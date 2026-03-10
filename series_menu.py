import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003894735143
ADMIN_ID = 7720165591

# ===== [2] متغيرات التخزين =====
fixed_message_id = None
MAX_EPISODES = 30
user_viewed = {}
completed_series = set()
last_episode_count = 0
bot_info = None 

# ===== [3] جلب البيانات =====
def get_series_list(db_query):
    return db_query("""
        SELECT 
            s.series_name,
            COUNT(*) as episode_count,
            MAX(s.created_at) as last_episode_date,
            MAX(s.ep_num) as max_episode,
            (SELECT v_id FROM videos WHERE series_name = s.series_name ORDER BY ep_num DESC LIMIT 1) as last_v_id
        FROM videos s
        WHERE s.series_name IS NOT NULL AND s.series_name != ''
        GROUP BY s.series_name
        ORDER BY s.series_name
    """)

# ===== [4] بناء الأزرار (3 في السطر) =====
def create_series_keyboard(series_list, user_id=None):
    keyboard = []
    row = []
    for item in series_list:
        s_name, count, last_date, max_ep, last_v_id = item
        
        btn_text = s_name
        if s_name in completed_series or max_ep >= MAX_EPISODES:
            btn_text += " ✅"
        else:
            is_new = False
            if last_date:
                if isinstance(last_date, str): last_date = datetime.fromisoformat(last_date)
                if (datetime.now() - last_date).total_seconds() < 86400:
                    if user_id not in user_viewed or s_name not in user_viewed[user_id] or user_viewed[user_id][s_name] < last_date:
                        is_new = True
            if is_new: btn_text += " 🆕"

        row.append(InlineKeyboardButton(btn_text, callback_data=f"v_{last_v_id}"))
        
        if len(row) == 3: 
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return keyboard

# ===== [5] التحديث التلقائي =====
async def update_series_channel(client, db_query, force=False):
    global fixed_message_id, last_episode_count, bot_info
    
    res = db_query("SELECT COUNT(*) FROM videos")
    current_count = res[0][0] if res else 0
    
    if not force and current_count <= last_episode_count: return

    if not bot_info:
        bot_info = await client.get_me()

    series_list = get_series_list(db_query)
    if not series_list: return
    
    text = "📺 **قائمة المسلسلات المتاحة**\n━━━━━━━━━━━━━━\n🔹 اضغط على المسلسل لمشاهدة الحلقة الأخيرة مباشرة في البوت"
    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list))

    try:
        if fixed_message_id:
            await client.edit_message_text(SERIES_CHANNEL, fixed_message_id, text, reply_markup=reply_markup)
        else:
            msg = await client.send_message(SERIES_CHANNEL, text, reply_markup=reply_markup)
            fixed_message_id = msg.id
        last_episode_count = current_count
    except Exception as e:
        logging.error(f"Error in update_menu: {e}")

# ===== [6] معالج الضغط (إرسال الفيديو مباشرة) =====
def register_handlers(app, db_query):
    
    @app.on_callback_query(filters.regex(r"^v_"))
    async def handle_view(client, cb):
        v_id = cb.data.replace("v_", "")
        user_id = cb.from_user.id
        
        # جلب بيانات الفيديو بالكامل
        res = db_query("SELECT file_id, series_name, ep_num, caption FROM videos WHERE v_id = %s", (v_id,))
        if not res:
            return await cb.answer("⚠️ لم يتم العثور على الحلقة!", show_alert=True)

        file_id, s_name, ep_num, caption = res[0]

        # تحديث علامة "جديد" للمستخدم
        if user_id not in user_viewed: user_viewed[user_id] = {}
        user_viewed[user_id][s_name] = datetime.now()

        # تحديث القائمة للمستخدم في القناة
        series_list = get_series_list(db_query)
        try:
            await cb.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup(create_series_keyboard(series_list, user_id))
            )
        except: pass
        
        # إرسال الفيديو مباشرة للمستخدم في الخاص
        await cb.answer(f"🍿 جاري إرسال حلقة {s_name}...", show_alert=False)
        try:
            await client.send_video(
                chat_id=user_id,
                video=file_id,
                caption=f"🎬 **{s_name}** - الحلقة {ep_num}\n\n{caption if caption else ''}"
            )
        except Exception as e:
            await cb.answer("⚠️ يرجى الضغط على Start في البوت أولاً!", show_alert=True)
            logging.error(f"Failed to send video: {e}")

    @app.on_callback_query(filters.regex(r"^del_") & filters.user(ADMIN_ID))
    async def admin_del(client, cb):
        s_name = cb.data.replace("del_", "")
        db_query("DELETE FROM videos WHERE series_name = %s", (s_name,), fetch=False)
        await cb.answer(f"🗑️ تم حذف {s_name}")
        await update_series_channel(client, db_query, force=True)

# ===== [7] وظائف الربط =====
def setup_series_menu(app, db_query):
    register_handlers(app, db_query)
    
    @app.on_message(filters.command("admin_menu") & filters.user(ADMIN_ID))
    async def show_admin(client, message):
        series_list = get_series_list(db_query)
        kb = [[InlineKeyboardButton(f"🗑️ {s[0]}", callback_data=f"del_{s[0]}")] for s in series_list]
        await message.reply("⚙️ إدارة القائمة الثابتة:", reply_markup=InlineKeyboardMarkup(kb))

    asyncio.get_event_loop().create_task(update_series_channel(app, db_query, force=True))

async def refresh_series_menu(client, db_query):
    await update_series_channel(client, db_query, force=True)
