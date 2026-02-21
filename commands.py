from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from db import db_execute
from config import NEW_BOT_USERNAME, CHANNEL_ID

async def start_handler(client: Client, message):
    if len(message.command) <= 1:
        await message.reply_text("مرحبًا! أنا بوت الإدارة الخاص بك.\n\nللمشاهدة أرسل الرابط أو استخدم رابط الحلقة.")
        return
    
    v_id = message.command[1]
    await send_video_with_list(client, message.chat.id, v_id)

async def send_video_with_list(client, chat_id, v_id):
    try:
        # جلب معلومات الفيديو من قاعدة البيانات
        video_info = db_execute("SELECT poster_id, poster_caption, duration, quality, ep_num FROM videos WHERE v_id=?", (v_id,))
        if not video_info: 
            await client.send_message(chat_id, "❌ عذراً، الحلقة غير متوفرة حالياً.")
            return
        poster_id, poster_caption, duration, quality, ep_num = video_info[0]

        # جلب كل الحلقات لنفس البوستر
        all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", (poster_id,))
        btns = []
        row = []
        for vid, num in all_ep:
            label = f"▶️ {num}" if vid == v_id else f"{num}"
            row.append(InlineKeyboardButton(label, callback_data=f"watch_{vid}"))
            if len(row) == 4:
                btns.append(row)
                row = []
        if row: btns.append(row)

        caption = f"{poster_caption if poster_caption else ''}\n🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 شاهد المزيد من الحلقات أسفل الفيديو"
        await client.send_photo(chat_id, poster_id, caption=caption, reply_markup=InlineKeyboardMarkup(btns))

    except Exception as e:
        await client.send_message(chat_id, f"❌ حدث خطأ: {e}")

async def callback_watch(client, query):
    v_id = query.data.split("_")[1]
    try:
        await query.message.delete()
    except: pass
    await send_video_with_list(client, query.from_user.id, v_id)
