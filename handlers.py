from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import db
from config import CHANNEL_ID, PUBLIC_CHANNEL

# استقبال الفيديوهات من القناة الخاصة
async def handle_video(client: Client, message):
    if not (message.video or message.document):
        return
    v_id = str(message.message_id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    mins, secs = divmod(duration_sec, 60)
    duration = f"{mins}:{secs:02d} دقيقة" if duration_sec else "غير محدد"
    db.db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", (v_id, duration, "waiting"), fetch=False)
    await message.reply_text("✅ تم استلام الفيديو. الآن أرسل بوستر الحلقة (صورة)")

# استقبال البوستر
async def handle_poster(client: Client, message):
    if not message.photo:
        return
    res = db.db_execute("SELECT v_id FROM videos WHERE status='waiting' ORDER BY rowid DESC LIMIT 1")
    if not res:
        return
    v_id = res[0][0]
    db.db_execute("UPDATE videos SET poster_id=?, status='awaiting_ep' WHERE v_id=?", (message.photo.file_id, v_id), fetch=False)
    await message.reply_text("🖼 تم حفظ البوستر. الآن أرسل رقم الحلقة:")

# استقبال رقم الحلقة
async def handle_episode_number(client: Client, message):
    if not message.text.isdigit():
        return
    res = db.db_execute("SELECT v_id, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res:
        return
    v_id, poster_id = res[0]
    ep_num = int(message.text)
    db.db_execute("UPDATE videos SET ep_num=?, status='awaiting_quality' WHERE v_id=?", (ep_num, v_id), fetch=False)
    await message.reply_text("🔧 اختر جودة الحلقة الآن (اكتب النص: 480p, 720p, 1080p)")

# استقبال الجودة
async def handle_quality(client: Client, message):
    quality = message.text.strip()
    if quality not in ["480p", "720p", "1080p"]:
        await message.reply_text("⚠️ الجودة غير صحيحة. الرجاء كتابة: 480p، 720p أو 1080p")
        return
    res = db.db_execute("SELECT v_id, poster_id, ep_num, duration, title FROM videos WHERE status='awaiting_quality' ORDER BY rowid DESC LIMIT 1")
    if not res:
        return
    v_id, poster_id, ep_num, duration, title = res[0]
    db.db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), fetch=False)

    # النشر في القناة العامة
    caption = f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
    if title:
        caption = f"🎬 {title}\n" + caption
    watch_link = f"https://t.me/{client.me.username}?start={v_id}"
    buttons = [[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]]
    await client.send_photo(PUBLIC_CHANNEL, poster_id, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    await message.reply_text(f"🚀 تم نشر الحلقة {ep_num} بنجاح!")
