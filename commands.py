from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import db

async def start_command(client: Client, message):
    if len(message.command) <= 1:
        await message.reply_text("مرحبًا! أرسل رابط الحلقة لبدء المشاهدة.")
        return
    v_id = message.command[1]
    video_info = db.db_execute("SELECT poster_id, ep_num, quality, title FROM videos WHERE v_id=?", (v_id,))
    if not video_info:
        await message.reply_text("❌ الحلقة غير موجودة حالياً.")
        return
    poster_id, ep_num, quality, title = video_info[0]
    caption = f"🎬 الحلقة {ep_num}\n✨ الجودة: {quality}"
    if title:
        caption = f"🎬 {title}\n" + caption
    watch_link = f"https://t.me/{client.me.username}?start={v_id}"
    buttons = [[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]]
    await client.send_photo(message.chat.id, poster_id, caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
