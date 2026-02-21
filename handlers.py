from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from main import app
from db import db_execute
from config import CHANNEL_ID, PUBLIC_CHANNEL

# استقبال الفيديو
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    mins, secs = divmod(duration_sec, 60)
    duration = f"{mins}:{secs:02d} دقيقة" if duration_sec else "غير محدد"
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", (v_id, duration, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\nالآن أرسل البوستر (الصورة) أو عنوان الحلقة")

# استقبال البوستر
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_execute("SELECT v_id FROM videos WHERE status='waiting' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    db_execute("UPDATE videos SET poster_id=?, status='awaiting_ep' WHERE v_id=?", (message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة:")

# استقبال رقم الحلقة
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit(): return
    res = db_execute("SELECT v_id, poster_id, duration FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1")
    if not res: return
    v_id, poster_id, duration = res[0]
    ep_num = int(message.text)
    db_execute("UPDATE videos SET ep_num=?, status='posted' WHERE v_id=?", (ep_num, v_id), fetch=False)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"

    # نشر تلقائي في القناة العامة
    if PUBLIC_CHANNEL:
        try:
            caption = f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: غير محددة\n\n📥 اضغط الزر لمشاهدة الحلقة"
            await client.send_photo(chat_id=PUBLIC_CHANNEL, photo=poster_id, caption=caption,
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]]))
            await message.reply_text(f"🚀 تم النشر بنجاح في @{PUBLIC_CHANNEL}")
        except Exception as e:
            await message.reply_text(f"⚠️ تم الحفظ ولكن فشل النشر: {e}")
    else:
        await message.reply_text(f"✅ تم الحفظ. الرابط المباشر:\n{watch_link}")
