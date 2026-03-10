import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003894735143
ADMIN_ID = 7720165591

# ===== [2] متغيرات الحالة =====
fixed_message_id = None
user_viewed = {}
completed_series = set()
last_episode_count = 0

# ===== [3] جلب البيانات من قاعدة البيانات =====
def get_series_list(db_query):
    """جلب قائمة المسلسلات مع معرف آخر حلقة مضافة لكل مسلسل"""
    series = db_query("""
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
    return series

# ===== [4] بناء الأزرار (3 مسلسلات في السطر) =====
def create_series_keyboard(series_list, user_id=None):
    keyboard = []
    row = []
    for item in series_list:
        s_name, count, last_date, max_ep, last_v_id = item
        
        # تحديد حالة الزر (جديد / مكتمل)
        btn_text = s_name
        if s_name in completed_series or max_ep >= 30: # 30 حلقة كحد افتراضي للاكتمال
            btn_text += " ✅"
        else:
            # التحقق من علامة "جديد" للمستخدم الحالي
            is_new = False
            if last_date:
                if isinstance(last_date, str): last_date = datetime.fromisoformat(last_date)
                # إذا كانت الحلقة خلال آخر 24 ساعة ولم يضغط عليها المستخدم بعد
                if (datetime.now() - last_date).total_seconds() < 86400:
                    if user_id not in user_viewed or s_name not in user_viewed[user_id] or user_viewed[user_id][s_name] < last_date:
                        is_new = True
            if is_new: btn_text += " 🆕"

        # إضافة الزر (يحتوي على معرف آخر حلقة لتوجيه المستخدم)
        row.append(InlineKeyboardButton(btn_text, callback_data=f"view_{last_v_id}_{s_name}"))
        
        # تنظيم 3 أزرار في كل سطر
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    if row: keyboard.append(row)
    return keyboard

# ===== [5] تحديث القائمة الثابتة في القناة =====
async def update_series_channel(client, db_query, force=False):
    global fixed_message_id, last_episode_count
    
    res = db_query("SELECT COUNT(*) FROM videos")
    current_count = res[0][0] if res else 0
    
    # لا يتم التحديث إلا إذا تغير عدد الحلقات أو طلبنا ذلك يدوياً
    if not force and current_count <= last_episode_count: return

    series_list = get_series_list(db_query)
    if not series_list: return
    
    text = (
        "📺 **قائمة المسلسلات المتاحة**\n"
        "━━━━━━━━━━━━━━\n"
        "🔹 اضغط على اسم المسلسل لمشاهدة آخر حلقة\n"
        "🔹 العلامة 🆕 تختفي بمجرد ضغطك على الزر"
    )
    
    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list))

    try:
        if fixed_message_id:
            await client.edit_message_text(SERIES_CHANNEL, fixed_message_id, text, reply_markup=reply_markup)
        else:
            msg = await client.send_message(SERIES_CHANNEL, text, reply_markup=reply_markup)
            fixed_message_id = msg.id
        last_episode_count = current_count
    except: 
        fixed_message_id = None # لإعادة المحاولة في حال حُذفت الرسالة

# ===== [6] المعالجات (توجيه + حذف) =====
def register_handlers(app, db_query):
    
    @app.on_callback_query(filters.regex(r"^view_"))
    async def handle_click(client, cb):
        data = cb.data.split("_")
        v_id, s_name = data[1], "_".join(data[2:])
        user_id = cb.from_user.id
        
        # 1. إخفاء علامة "جديد" لهذا المستخدم فوراً
        if user_id not in user_viewed: user_viewed[user_id] = {}
        user_viewed[user_id][s_name] = datetime.now()
        
        # تحديث الأزرار للمستخدم في القناة (تغيير محلي)
        series_list = get_series_list(db_query)
        try:
            await cb.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup(create_series_keyboard(series_list, user_id))
            )
        except: pass
        
        # 2. التحويل المباشر لصفحة المشاهدة
        me = await client.get_me()
        url = f"https://t.me/{me.username}?start={v_id}"
        await cb.answer("جاري نقلك لأحدث حلقة...", show_alert=False)
        await client.send_message(user_id, f"🎬 تم اختيار **{s_name}**\n\nاضغط على الرابط للمشاهدة فوراً:\n{url}")

    @app.on_callback_query(filters.regex(r"^delete_") & filters.user(ADMIN_ID))
    async def admin_delete(client, cb):
        s_name = cb.data.replace("delete_", "")
        db_query("DELETE FROM videos WHERE series_name = %s", (s_name,), fetch=False)
        await cb.answer(f"🗑️ تم حذف {s_name} وتحديث القائمة")
        await update_series_channel(client, db_query, force=True)

# ===== [7] الإعداد والتشغيل =====
def setup_series_menu(app, db_query):
    register_handlers(app, db_query)
    
    # أمر الإدارة لفتح قائمة الحذف
    @app.on_message(filters.command("admin_menu") & filters.user(ADMIN_ID))
    async def show_admin(client, message):
        series_list = get_series_list(db_query)
        kb = [[InlineKeyboardButton(f"🗑️ حذف {s[0]}", callback_data=f"delete_{s[0]}")] for s in series_list]
        await message.reply("🛠️ اختر المسلسل المراد حذفه نهائياً من القائمة:", reply_markup=InlineKeyboardMarkup(kb))

    # التحديث الأول عند التشغيل
    asyncio.get_event_loop().create_task(update_series_channel(app, db_query, force=True))

async def refresh_series_menu(client, db_query):
    """دالة الربط مع الملف الرئيسي"""
    await update_series_channel(client, db_query, force=True)
