from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import db
from config import CHANNEL_ID

async def start_handler(client: Client, message):
    if len(message.command) <= 1:
        await message.reply_text("أهلاً بك! أرسل رابط الحلقة للمشاهدة.")
        return

    v_id = message.command[1]
    await send_video_with_list(client, message.chat.id, v_id)

async def send_video_with_list(client: Client, chat_id, v_id):
    video_info = db.db_execute("SELECT poster_id, duration, quality, ep_num FROM videos WHERE v_id=?", (v_id,))
    if not video_info: return
    poster_id, duration, quality, ep_num = video_info[0]

    # إرسال الفيديو
    await client.copy_message(chat_id, CHANNEL_ID, int(v_id), protect_content=True)

    # جلب كل الحلقات لنفس البوستر
    all_ep = db.db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", (poster_id,))
    btns = []
    row = []
    for vid, num in all_ep:
        label = f"▶️ {num}" if vid == v_id else f"{num}"
        row.append(InlineKeyboardButton(label, callback_data=f"watch_{vid}"))
        if len(row) == 4:
            btns.append(row)
            row = []
    if row: btns.append(row)

    caption = f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 شاهد المزيد من الحلقات أسفل الفيديو"
    await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(btns))

async def watch_callback(client, query):
    v_id = query.data.split("_")[1]
    try:
        await query.message.delete()
    except: pass
    await send_video_with_list(client, query.from_user.id, v_id)
