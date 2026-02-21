from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import db_execute

def register_commands(app):
    # بدء البوت في المحادثة الخاصة
    @app.on_message(filters.private & filters.command("start"))
    async def start_handler(client, message):
        if len(message.command) <= 1:
            await message.reply_text("مرحبًا! أرسل الرابط أو ID الحلقة للمشاهدة.")
            return

        v_id = message.command[1]
        await send_video_with_list(client, message.chat.id, v_id)

    # التعامل مع أزرار الحلقات
    @app.on_callback_query(filters.regex(r"^watch_"))
    async def watch_episode(client, query):
        v_id = query.data.split("_")[1]
        try:
            await query.message.delete()
        except: pass
        await send_video_with_list(client, query.from_user.id, v_id)

    async def send_video_with_list(client, chat_id, v_id):
        video_info = db_execute("SELECT poster_id, title, ep_num, quality FROM videos WHERE v_id=?", (v_id,))
        if not video_info:
            await client.send_message(chat_id, "❌ عذراً، الحلقة غير متوفرة حالياً.")
            return
        poster_id, title, ep_num, quality = video_info[0]

        caption = f"🎬 الحلقة {ep_num}\n✨ الجودة: {quality}"
        if title:
            caption = f"{title}\n" + caption
        watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
        await client.send_photo(chat_id, poster_id, caption=caption,
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ شاهد الحلقة الآن", url=watch_link)]]))

        all_eps = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? ORDER BY ep_num ASC", (poster_id,))
        if all_eps and len(all_eps) > 1:
            btns = []
            row = []
            for vid, num in all_eps:
                label = f"▶️ {num}" if vid == v_id else f"{num}"
                row.append(InlineKeyboardButton(label, callback_data=f"watch_{vid}"))
                if len(row) == 4:
                    btns.append(row)
                    row = []
            if row: btns.append(row)
            await client.send_message(chat_id, "شاهد المزيد من الحلقات:", reply_markup=InlineKeyboardMarkup(btns))
