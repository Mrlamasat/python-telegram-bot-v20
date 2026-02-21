diff --git a/handlers.py b/handlers.py
index 745973e7f9dbfeac4fb98eca630fdb2a2c81790b..05cef7a81d30720c34b18aa38985a3a45d79791e 100644
--- a/handlers.py
+++ b/handlers.py
@@ -1,55 +1,97 @@
-from pyrogram import filters
-from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
-from config import CHANNEL_ID, PUBLIC_CHANNEL
+from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
+from telegram.error import RetryAfter
+from telegram.ext import ContextTypes
+
+from config import PUBLIC_CHANNEL
 from db import db_execute
-from pyrogram.errors import FloodWait
 
-async def handle_video(client, message):
-    v_id = str(message.id)
-    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
+
+def _public_channel_target() -> str:
+    channel = PUBLIC_CHANNEL.strip()
+    if channel.startswith("@"):
+        return channel
+    return f"@{channel}" if channel else ""
+
+
+async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
+    message = update.effective_message
+    if not message:
+        return
+
+    v_id = str(message.message_id)
+    duration_sec = 0
+    if message.video:
+        duration_sec = message.video.duration or 0
     mins, secs = divmod(duration_sec, 60)
     duration = f"{mins}:{secs:02d} دقيقة" if duration_sec else "غير محدد"
+
     db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", (v_id, duration, "waiting"), fetch=False)
     await message.reply_text("✅ تم استلام الفيديو.\nالآن أرسل البوستر (صورة)")
 
-async def handle_poster(client, message):
+
+async def handle_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
+    message = update.effective_message
+    if not message or not message.photo:
+        return
+
     res = db_execute("SELECT v_id FROM videos WHERE status='waiting' ORDER BY rowid DESC LIMIT 1")
-    if not res: return
+    if not res:
+        return
+
     v_id = res[0][0]
-    db_execute("UPDATE videos SET poster_id=?, status='awaiting_ep' WHERE v_id=?", (message.photo.file_id, v_id), fetch=False)
+    poster_file_id = message.photo[-1].file_id
+    db_execute("UPDATE videos SET poster_id=?, status='awaiting_ep' WHERE v_id=?", (poster_file_id, v_id), fetch=False)
     await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة:")
 
-async def handle_ep_number(client, message):
-    if not message.text.isdigit(): return
-    res = db_execute("SELECT v_id, poster_id, duration FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1")
-    if not res: return
-    v_id, poster_id, duration = res[0]
+
+async def handle_ep_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
+    message = update.effective_message
+    if not message or not message.text or not message.text.isdigit():
+        return
+
+    res = db_execute("SELECT v_id FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1")
+    if not res:
+        return
+
+    v_id = res[0][0]
     ep_num = int(message.text)
     db_execute("UPDATE videos SET ep_num=?, status='awaiting_quality' WHERE v_id=?", (ep_num, v_id), fetch=False)
     await message.reply_text("✅ رقم الحلقة تم حفظه.\n📌 اختر الجودة بإرسال نص مثل: 720p أو 1080p")
 
-async def handle_quality(client, message):
+
+async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
+    message = update.effective_message
+    if not message or not message.text:
+        return
+
     quality = message.text.strip()
+    if not quality or quality.isdigit():
+        return
+
     res = db_execute("SELECT v_id, poster_id, ep_num, duration FROM videos WHERE status='awaiting_quality' ORDER BY rowid DESC LIMIT 1")
-    if not res: return
+    if not res:
+        return
+
     v_id, poster_id, ep_num, duration = res[0]
     db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), fetch=False)
-    watch_link = f"https://t.me/{client.me.username}?start={v_id}"
-    
-    # نشر تلقائي في القناة العامة
-    if PUBLIC_CHANNEL:
+
+    me = await context.bot.get_me()
+    watch_link = f"https://t.me/{me.username}?start={v_id}"
+
+    target_channel = _public_channel_target()
+    if target_channel:
         caption = f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر لمشاهدة الحلقة"
         try:
-            await client.send_photo(
-                chat_id=PUBLIC_CHANNEL, 
-                photo=poster_id, 
+            await context.bot.send_photo(
+                chat_id=target_channel,
+                photo=poster_id,
                 caption=caption,
-                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
+                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]]),
             )
-            await message.reply_text(f"🚀 تم النشر بنجاح في @{PUBLIC_CHANNEL}")
-        except FloodWait as e:
-            await message.reply_text(f"⚠️ انتظر {e.value} ثانية ثم حاول مرة أخرى.")
+            await message.reply_text(f"🚀 تم النشر بنجاح في {target_channel}")
+        except RetryAfter as e:
+            await message.reply_text(f"⚠️ انتظر {int(e.retry_after)} ثانية ثم حاول مرة أخرى.")
         except Exception as e:
             await message.reply_text(f"⚠️ تم الحفظ ولكن فشل النشر: {e}")
     else:
         await message.reply_text(f"✅ تم الحفظ. الرابط المباشر:\n{watch_link}")
