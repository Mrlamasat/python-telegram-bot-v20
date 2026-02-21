from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from main import app
from db import db_execute
from config import CHANNEL_ID, PUBLIC_CHANNEL, NEW_BOT_USERNAME

# /start
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text("مرحبًا! أنا بوت الإدارة الخاص بك.\nالأوامر المتاحة:\n/list\nأرسل رابط الحلقة لمشاهدتها.")
        return

    v_id = message.command[1]
    await send_video_with_list(client, message.chat.id, v_id)

# إرسال الفيديو مع قائمة الحلقات
async def send_video_with_list(client, chat_id, v_id):
    try:
        video_info = db_execute("SELECT poster_id, duration, quality, ep_num FROM videos WHERE v_id=?", (v_id,))
        if not video_info:
            await client.send_message(chat_id, f"❌ الحلقة غير موجودة! انتقل للبوت الجديد: https://t.me/{NEW_BOT_USERNAME}")
            return
        poster_id, duration, quality, ep_num = video_info[0]

        # إرسال الفيديو/صورة
        await client.send_photo(chat_id, poster_id,
                                caption=f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\nشاهد المزيد من الحلقات أسفل الفيديو",
                                reply_markup=await generate_episode_buttons(client, poster_id, v_id))

    except Exception as e:
        await client.send_message(chat_id, f"❌ حدث خطأ: {e}")

# توليد أزرار الحلقات
async def generate_episode_buttons(client, poster_id, current_v_id):
    all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", (poster_id,))
    btns = []
    row = []
    for vid, num in all_ep:
        label = f"▶️ {num}" if vid == current_v_id else f"{num}"
        row.append(InlineKeyboardButton(label, callback_data=f"watch_{vid}"))
        if len(row) == 4:
            btns.append(row)
            row = []
    if row: btns.append(row)
    # إضافة زر "أعجبني" و "الانتقال للمشاهدة"
    btns.append([InlineKeyboardButton("👍 أعجبني", callback_data="like"),
                 InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{(await client.get_me()).username}?start={current_v_id}")])
    return InlineKeyboardMarkup(btns)

# التعامل مع الضغط على أي حلقة
@app.on_callback_query()
async def callback_query_handler(client, query):
    data = query.data
    if data.startswith("watch_"):
        v_id = data.split("_")[1]
        try: await query.message.delete()
        except: pass
        await send_video_with_list(client, query.from_user.id, v_id)
    elif data == "like":
        await query.answer("شكراً لك 👍")
