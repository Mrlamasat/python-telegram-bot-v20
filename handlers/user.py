from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..db import db_execute
from ..config import PUBLIC_CHANNEL, BOT_USERNAME

async def register_user_handlers(app):

    # ===== التحقق من الاشتراك في القناة =====
    async def check_subscription(client, user_id):
        if not PUBLIC_CHANNEL:
            return True
        try:
            member = await client.get_chat_member(PUBLIC_CHANNEL, user_id)
            return member.status not in ["left", "kicked"]
        except:
            return False

    # ===== /start =====
    @app.on_message(filters.command("start") & filters.private)
    async def start_handler(client, message):
        if len(message.command) <= 1:
            await message.reply_text("أهلاً! أرسل رابط الحلقة للمشاهدة.")
            return
        v_id = message.command[1]
        is_subscribed = await check_subscription(client, message.from_user.id)
        if not is_subscribed:
            await message.reply_text(f"❌ يجب الاشتراك في @{PUBLIC_CHANNEL} لمشاهدة الحلقة")
            return
        await send_video_with_list(client, message.chat.id, v_id)

    # ===== إرسال الفيديو مع قائمة الحلقات =====
    async def send_video_with_list(client, chat_id, v_id):
        video_info = db_execute("SELECT poster_id, title, ep_num, duration, quality FROM videos WHERE v_id=?", (v_id,))
        if not video_info: 
            await client.send_message(chat_id, "❌ عذراً، الحلقة غير متوفرة حالياً.")
            return
        poster_id, title, ep_num, duration, quality = video_info[0]
        caption = f"{title}\n🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}" if title else f"🎬 الحلقة {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
        await client.send_photo(chat_id, poster_id, caption=caption)
        # جلب كل الحلقات لنفس البوستر
        all_ep = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", (poster_id,))
        if all_ep and len(all_ep) > 1:
            btns = []
            row = []
            for vid, num in all_ep:
                label = f"{num}" if vid != v_id else f"▶️ {num}"
                row.append(InlineKeyboardButton(label, callback_data=f"watch_{vid}"))
                if len(row) == 4:
                    btns.append(row)
                    row = []
            if row: btns.append(row)
            await client.send_message(chat_id, "📥 شاهد المزيد من الحلقات:", reply_markup=InlineKeyboardMarkup(btns))

    # ===== الضغط على أي حلقة =====
    @app.on_callback_query(filters.regex(r"^watch_"))
    async def watch_episode(client, query):
        v_id = query.data.split("_")[1]
        try: await query.message.delete()
        except: pass
        is_subscribed = await check_subscription(client, query.from_user.id)
        if not is_subscribed:
            await query.message.reply(f"❌ يجب الاشتراك في @{PUBLIC_CHANNEL} لمشاهدة الحلقة")
            return
        await send_video_with_list(client, query.from_user.id, v_id)
        await query.answer()
