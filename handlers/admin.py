from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..db import db_execute
from ..utils import format_duration
from ..config import CHANNEL_ID, PUBLIC_CHANNEL

async def register_admin_handlers(app):

    # ===== استقبال الفيديو =====
    @app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
    async def receive_video(client, message):
        v_id = str(message.id)
        duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
        duration = format_duration(duration_sec)
        db_execute(
            "INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
            (v_id, duration, "waiting"), fetch=False
        )
        await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\nالآن أرسل البوستر مع العنوان (اختياري)")

    # ===== استقبال البوستر =====
    @app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
    async def receive_poster(client, message):
        res = db_execute("SELECT v_id FROM videos WHERE status='waiting' ORDER BY rowid DESC LIMIT 1")
        if not res: return
        v_id = res[0][0]
        # نحاول أخذ عنوان من رسالة البوستر إن كان موجود
        title = message.caption if message.caption else ""
        db_execute(
            "UPDATE videos SET poster_id=?, title=?, status='awaiting_ep' WHERE v_id=?",
            (message.photo.file_id, title, v_id), fetch=False
        )
        await message.reply_text(f"🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة:")

    # ===== استقبال رقم الحلقة =====
    @app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
    async def receive_ep_number(client, message):
        if not message.text.isdigit(): return
        res = db_execute("SELECT v_id, poster_id, title, duration FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1")
        if not res: return
        v_id, poster_id, title, duration = res[0]
        ep_num = int(message.text)
        db_execute("UPDATE videos SET ep_num=?, status='awaiting_quality' WHERE v_id=?", (ep_num, v_id), fetch=False)
        # إرسال رسالة لطلب الجودة
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("480p", callback_data=f"set_quality_480_{v_id}")],
            [InlineKeyboardButton("720p", callback_data=f"set_quality_720_{v_id}")],
            [InlineKeyboardButton("1080p", callback_data=f"set_quality_1080_{v_id}")]
        ])
        await message.reply_text("📺 اختر جودة الحلقة:", reply_markup=kb)

    # ===== استقبال اختيار الجودة =====
    @app.on_callback_query(filters.regex(r"^set_quality_"))
    async def set_quality(client, query):
        parts = query.data.split("_")
        quality = parts[2]
        v_id = parts[3]
        db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), fetch=False)
        # نشر تلقائي في القناة العامة
        video_info = db_execute("SELECT poster_id, title, ep_num, duration FROM videos WHERE v_id=?", (v_id,))
        if not video_info: return
        poster_id, title, ep_num, duration = video_info[0]
        caption = f"{title}\n🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}" if title else f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
        watch_link = f"https://t.me/{client.me.username}?start={v_id}"
        if PUBLIC_CHANNEL:
            try:
                await client.send_photo(
                    chat_id=PUBLIC_CHANNEL,
                    photo=poster_id,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("👍 اعجبني", callback_data=f"like_{v_id}")],
                        [InlineKeyboardButton("▶️ شاهد الحلقة الآن", url=watch_link)]
                    ])
                )
                await query.message.edit_text(f"🚀 تم النشر بنجاح في @{PUBLIC_CHANNEL}")
            except Exception as e:
                await query.message.edit_text(f"⚠️ تم الحفظ ولكن فشل النشر: {e}")
        else:
            await query.message.edit_text(f"✅ تم الحفظ. الرابط المباشر:\n{watch_link}")
        await query.answer()
