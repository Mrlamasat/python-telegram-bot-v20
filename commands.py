diff --git a/commands.py b/commands.py
index 18266485c13a8bc43f9329175c6d648db08f67fe..cd5f14233f6ff0f56fd5a31f78d9e74378647ca4 100644
--- a/commands.py
+++ b/commands.py
@@ -1,42 +1,57 @@
-from pyrogram import filters
-from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
+from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
+from telegram.error import TelegramError
+from telegram.ext import ContextTypes
+
 from db import db_execute
-from config import CHANNEL_ID
 
-async def start_handler(client, message):
-    if len(message.command) <= 1:
+
+async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
+    message = update.effective_message
+    if not message:
+        return
+
+    if len(context.args) < 1:
         await message.reply_text("مرحبًا! أرسل الرابط أو الرقم لمشاهدة الحلقة.")
         return
 
-    v_id = message.command[1]
-    await send_video_with_list(client, message.chat.id, v_id)
+    v_id = context.args[0]
+    await send_video_with_list(context, message.chat_id, v_id)
+
 
-async def send_video_with_list(client, chat_id, v_id):
+async def send_video_with_list(context: ContextTypes.DEFAULT_TYPE, chat_id: int, v_id: str):
     video_info = db_execute("SELECT poster_id, duration, quality, ep_num FROM videos WHERE v_id=?", (v_id,))
-    if not video_info: 
-        await client.send_message(chat_id, "❌ الحلقة غير متوفرة.")
+    if not video_info:
+        await context.bot.send_message(chat_id, "❌ الحلقة غير متوفرة.")
         return
-    
+
     poster_id, duration, quality, ep_num = video_info[0]
     all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", (poster_id,))
-    
-    # زرار الحلقات
+
     btns = []
     row = []
     for vid, num in all_ep:
         label = f"▶️ {num}" if vid == v_id else f"{num}"
         row.append(InlineKeyboardButton(label, callback_data=f"watch_{vid}"))
         if len(row) == 4:
             btns.append(row)
             row = []
-    if row: btns.append(row)
-    
+    if row:
+        btns.append(row)
+
     caption = f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 شاهد المزيد من الحلقات أسفل الفيديو"
-    await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(btns))
+    await context.bot.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(btns))
+
 
-async def callback_watch(client, query):
-    v_id = query.data.split("_")[1]
+async def callback_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
+    query = update.callback_query
+    if not query or not query.data:
+        return
+
+    await query.answer()
+    v_id = query.data.split("_", 1)[1]
     try:
         await query.message.delete()
-    except: pass
-    await send_video_with_list(client, query.from_user.id, v_id)
+    except TelegramError:
+        pass
+
+    await send_video_with_list(context, query.from_user.id, v_id)
