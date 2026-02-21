from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import db_execute
from config import CHANNEL_ID, PUBLIC_CHANNEL
import asyncio

def register_handlers(app):

    # استقبال الفيديو
    @app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
    async def receive_video(client, message):
        v_id = str(message.id)
        duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
        mins, secs = divmod(duration_sec, 60)
        duration = f"{mins}:{secs:02d} دقيقة" if duration_sec else "غير محدد"

        db_execute(
            "INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)",
            (v_id, duration, "waiting"),
            fetch=False
        )
        await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\nالآن أرسل البوستر (الصورة)")

    # استقبال البوستر
    @app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
    async def receive_poster(client, message):
        res = db_execute("SELECT v_id FROM videos WHERE status='waiting' ORDER BY rowid DESC LIMIT 1")
        if not res:
            return
        v_id = res[0][0]
        db_execute(
            "UPDATE videos SET poster_id=?, status='awaiting_ep' WHERE v_id=?",
            (message.photo.file_id, v_id),
            fetch=False
        )
        await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة:")

    # استقبال رقم الحلقة
    @app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
    async def receive_ep_number(client, message):
        if not message.text.isdigit():
            return
        res = db_execute("SELECT v_id, poster_id, duration FROM videos WHERE status='awaiting_ep' ORDER BY rowid DESC LIMIT 1")
        if not res:
            return
        v_id, poster_id, duration = res[0]
        ep_num = int(message.text)
        db_execute("UPDATE videos SET ep_num=?, status='awaiting_quality' WHERE v_id=?", (ep_num, v_id), fetch=False)
        await message.reply_text("🔧 اختر الجودة الآن (مثال: 720p أو 1080p):")

    # استقبال الجودة
    @app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
    async def receive_quality(client, message):
        res = db_execute("SELECT v_id, poster_id, duration, ep_num FROM videos WHERE status='awaiting_quality' ORDER BY rowid DESC LIMIT 1")
        if not res:
            return
        v_id, poster_id, duration, ep_num = res[0]
        quality = message.text.strip()
        db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), fetch=False)

        # نشر الحلقة في القناة العامة
        watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
        caption = f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر لمشاهدة الحلقة"
        if PUBLIC_CHANNEL:
            await client.send_photo(
                chat_id=PUBLIC_CHANNEL,
                photo=poster_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
            )
        await message.reply_text(f"🚀 تم نشر الحلقة بنجاح.\nالرابط: {watch_link}")

    # أوامر /start
    @app.on_message(filters.command("start") & filters.private)
    async def start_handler(client, message):
        if len(message.command) == 1:
            await message.reply_text("مرحبًا! أرسل رابط الحلقة للمشاهدة.")
            return
        v_id = message.command[1]
        await send_video_with_list(client, message.chat.id, v_id)

    # إرسال الفيديو والقائمة
    async def send_video_with_list(client, chat_id, v_id):
        video_info = db_execute("SELECT poster_id, duration, quality, ep_num FROM videos WHERE v_id=?", (v_id,))
        if not video_info:
            await client.send_message(chat_id, "❌ عذراً، الحلقة غير متوفرة حالياً.")
            return
        poster_id, duration, quality, ep_num = video_info[0]
        watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"

        await client.send_photo(chat_id, poster_id, caption=f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]]))

        # جميع الحلقات لنفس البوستر
        all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", (poster_id,))
        if all_ep and len(all_ep) > 1:
            btns = []
            row = []
            for vid, num in all_ep:
                label = f"▶️ {num}" if vid == v_id else f"{num}"
                row.append(InlineKeyboardButton(label, callback_data=f"watch_{vid}"))
                if len(row) == 4:
                    btns.append(row)
                    row = []
            if row:
                btns.append(row)
            await client.send_message(chat_id, "📺 شاهد المزيد من الحلقات:", reply_markup=InlineKeyboardMarkup(btns))

    # التعامل مع الضغط على أي حلقة
    @app.on_callback_query(filters.regex(r"^watch_"))
    async def watch_episode(client, query):
        v_id = query.data.split("_")[1]
        try:
            await query.message.delete()
        except: pass
        await send_video_with_list(client, query.from_user.id, v_id)
