from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from db import db_execute
from config import CHANNEL_ID, PUBLIC_CHANNEL
import asyncio

async def handle_video(client: Client, message):
    # حفظ الفيديو في قاعدة البيانات
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    mins, secs = divmod(duration_sec, 60)
    duration = f"{mins}:{secs:02d} دقيقة" if duration_sec else "غير محدد"

    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
               (v_id, duration, "waiting"), fetch=False)
    
    await message.reply_text("✅ تم استلام الفيديو.\nالآن أرسل صورة البوستر (إجباري)")

async def handle_poster(client: Client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status='waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]

    caption = message.caption if message.caption else None
    db_execute("UPDATE videos SET poster_id=?, poster_caption=?, status='awaiting_ep' WHERE v_id=?",
               (message.photo.file_id, caption, v_id), fetch=False)

    await message.reply_text("🖼 تم حفظ البوستر.\n🔢 الآن أرسل رقم الحلقة:")

async def handle_ep_number(client: Client, message):
    if not message.text.isdigit(): return
    res = db_execute("SELECT v_id, poster_id, poster_caption, duration FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id, poster_id, poster_caption, duration = res[0]
    ep_num = int(message.text)
    db_execute("UPDATE videos SET ep_num=?, status='awaiting_quality' WHERE v_id=?", (ep_num, v_id), fetch=False)
    
    await message.reply_text(f"✅ رقم الحلقة {ep_num} تم حفظه.\n🎥 أرسل الآن جودة الحلقة (مثال: 720p, 1080p)")

async def handle_quality(client: Client, message):
    quality = message.text.strip()
    if not quality: return
    res = db_execute("SELECT v_id, poster_id, poster_caption, ep_num, duration FROM videos WHERE status='awaiting_quality' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id, poster_id, poster_caption, ep_num, duration = res[0]

    db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), fetch=False)

    # نشر تلقائي في القناة العامة
    watch_link = f"https://t.me/{await client.get_me().username}?start={v_id}"
    caption = f"{poster_caption if poster_caption else ''}\n🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر لمشاهدة الحلقة"

    if PUBLIC_CHANNEL:
        await client.send_photo(chat_id=PUBLIC_CHANNEL, photo=poster_id,
                                caption=caption,
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]]))
        await message.reply_text(f"🚀 تم النشر بنجاح في @{PUBLIC_CHANNEL}")
