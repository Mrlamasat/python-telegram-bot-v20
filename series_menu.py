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

# ===== [3] جلب البيانات من قاعدة البيانات =====
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

# ===== [4] بناء الأزرار (أيقونات واضحة وروابط مباشرة) =====
def create_series_keyboard(series_list, bot_username):
    keyboard = []
    row = []
    for item in series_list:
        s_name, count, last_date, max_ep, last_v_id = item
        
        btn_text = s_name
        
        # ✅ وسم المسلسلات المكتملة (الحلقة الأخيرة)
        if s_name in completed_series or max_ep >= MAX_EPISODES:
            btn_text += " ✅"
        else:
            # 🔥 وسم "نيو" للحلقات الجديدة (آخر 24 ساعة)
            if last_date:
                if isinstance(last_date, str): last_date = datetime.fromisoformat(last_date)
                if (datetime.now() - last_date).total_seconds() < 86400:
                    btn_text += " 🔥"

        # الرابط المباشر للبوت للمشاهدة
        direct_url = f"https://t.me/{bot_username}?start={last_v_id}"
        row.append(InlineKeyboardButton(btn_text, url=direct_url))
        
        if len(row) == 3: 
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return keyboard

# ===== [5] التحديث التلقائي للقناة بالنص الجديد الواضح =====
async def update_series_channel(client, db_query, force=False):
    global fixed_message_id, last_episode_count, bot_info
    
    res = db_query("SELECT COUNT(*) FROM videos")
    current_count = res[0][0] if res else 0
    if not force and current_count <= last_episode_count: return

    if not bot_info:
        bot_info = await client.get_me()

    series_list = get_series_list(db_query)
    if not series_list: return
    
    # النص النهائي والمعدل بناءً على طلبك يا محمد
    text = (
        "🎬 **مكتبة المسلسلات الحصرية**\n"
        "━━━━━━━━━━━━━━━\n"
        "اضغط على اسم المسلسل للمشاهدة الفورية 👇\n\n"
        "✅ **تعني: تم اكتمال المسلسل (الحلقة الأخيرة)**\n"
        "🔥 **تعني: توجد حلقة جديدة مضافة الآن**"
    )

    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list, bot_info.username))

    try:
        if fixed_message_id:
            await client.edit_message_text(SERIES_CHANNEL, fixed_message_id, text, reply_markup=reply_markup)
        else:
            msg = await client.send_message(SERIES_CHANNEL, text, reply_markup=reply_markup)
            fixed_message_id = msg.id
        last_episode_count = current_count
    except Exception as e:
        logging.error(f"Error in update_menu: {e}")

# ===== [6] لوحة الإدارة (حذف وتعيين منتهي) =====
def register_handlers(app, db_query):
    
    @app.on_message(filters.command("admin_menu") & filters.user(ADMIN_ID))
    async def show_admin(client, message):
        series_list = get_series_list(db_query)
        kb = []
        for s in series_list:
            s_name = s[0]
            kb.append([
                InlineKeyboardButton(f"🗑️ حذف {s_name}", callback_data=f"del_{s_name}"),
                InlineKeyboardButton(f"✅ تعيين منتهي", callback_data=f"complete_{s_name}")
            ])
        await message.reply("⚙️ **لوحة إدارة المسلسلات**", reply_markup=InlineKeyboardMarkup(kb))

    @app.on_callback_query(filters.regex(r"^(del_|complete_)") & filters.user(ADMIN_ID))
    async def handle_admin_actions(client, cb):
        if cb.data.startswith("del_"):
            s_name = cb.data.replace("del_", "")
            db_query("DELETE FROM videos WHERE series_name = %s", (s_name,), fetch=False)
            await cb.answer(f"🗑️ تم حذف {s_name}")
        elif cb.data.startswith("complete_"):
            s_name = cb.data.replace("complete_", "")
            completed_series.add(s_name)
            await cb.answer(f"✅ تم تعيين {s_name} كمنتهي")
        
        await update_series_channel(client, db_query, force=True)

# ===== [7] وظائف الربط =====
def setup_series_menu(app, db_query):
    register_handlers(app, db_query)
    asyncio.get_event_loop().create_task(update_series_channel(app, db_query, force=True))

async def refresh_series_menu(client, db_query):
    await update_series_channel(client, db_query, force=True)
