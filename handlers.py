from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import db_execute
from config import CHANNEL_ID, PUBLIC_CHANNEL

pending_video = {}

def register_handlers(app):
    # استقبال الفيديو
    @app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
    async def receive_video(client, message):
        v_id = str(message.id)
        pending_video[message.from_user.id] = {"v_id": v_id, "status": "video"}
        await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\nالخطوة التالية: أرسل البوستر (الصورة)")

    # استقبال البوستر + وصف اختياري
    @app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
    async def receive_poster(client, message):
        user_id = message.from_user.id
        if user_id not in pending_video or pending_video[user_id]["status"] != "video":
            return
        pending_video[user_id]["poster_id"] = message.photo.file_id
        pending_video[user_id]["status"] = "poster"
        await message.reply_text("🖼 تم حفظ البوستر.\nيمكنك إضافة وصف للصورة (اختياري) أو أرسل /skip للمتابعة.")

    # استقبال وصف البوستر (اختياري)
    @app.on_message(filters.chat(CHANNEL_ID) & filters.text)
    async def receive_title(client, message):
        user_id = message.from_user.id
        if user_id not in pending_video or pending_video[user_id]["status"] != "poster":
            return
        text = message.text
        if text.lower() == "/skip":
            text = None
        pending_video[user_id]["title"] = text
        pending_video[user_id]["status"] = "title_done"
        await message.reply_text("🔢 الآن أرسل رقم الحلقة (رقم صحيح)")

    # استقبال رقم الحلقة
    @app.on_message(filters.chat(CHANNEL_ID) & filters.text)
    async def receive_ep_number(client, message):
        user_id = message.from_user.id
        if user_id not in pending_video or pending_video[user_id]["status"] != "title_done":
            return
        if not message.text.isdigit():
            await message.reply_text("⚠️ يجب أن يكون رقم الحلقة رقماً صحيحاً.")
            return
        pending_video[user_id]["ep_num"] = int(message.text)
        pending_video[user_id]["status"] = "ep_done"
        await message.reply_text("🎚 الآن أرسل الجودة (مثال: 720p)")

    # استقبال الجودة
    @app.on_message(filters.chat(CHANNEL_ID) & filters.text)
    async def receive_quality(client, message):
        user_id = message.from_user.id
        if user_id not in pending_video or pending_video[user_id]["status"] != "ep_done":
            return
        quality = message.text.strip()
        if not quality:
            await message.reply_text("⚠️ الجودة مطلوبة، يرجى إدخالها.")
            return
        data = pending_video[user_id]
        data["quality"] = quality
        data["status"] = "done"

        # حفظ في قاعدة البيانات
        db_execute(
            "INSERT OR REPLACE INTO videos (v_id, poster_id, title, ep_num, quality, status) VALUES (?, ?, ?, ?, ?, ?)",
            (data["v_id"], data["poster_id"], data.get("title"), data["ep_num"], data["quality"], "posted"),
            fetch=False
        )

        # نشر في القناة العامة
        watch_link = f"https://t.me/{(await client.get_me()).username}?start={data['v_id']}"
        caption = f"🎬 الحلقة {data['ep_num']}\n✨ الجودة: {data['quality']}"
        if data.get("title"):
            caption = f"{data['title']}\n" + caption

        try:
            if PUBLIC_CHANNEL:
                await client.send_photo(
                    chat_id=PUBLIC_CHANNEL,
                    photo=data["poster_id"],
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("▶️ اضغط هنا لمشاهدة الحلقة", url=watch_link)]
                    ])
                )
            await message.reply_text(f"🚀 تم النشر بنجاح. الرابط المباشر:\n{watch_link}")
        except Exception as e:
            await message.reply_text(f"⚠️ تم الحفظ ولكن فشل النشر: {e}")

        del pending_video[user_id]
