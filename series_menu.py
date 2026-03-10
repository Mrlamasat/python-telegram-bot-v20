# ===== series_menu.py =====
import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003894735143
ADMIN_ID = 7720165591

# ===== [2] متغيرات التخزين =====
fixed_message_id = None
MAX_EPISODES = 30

# ===== [3] تخزين حالة المشاهدة =====
user_viewed = {}
completed_series = set()

# ===== [4] آخر عدد للحلقات =====
last_episode_count = 0

# ===== [5] دوال مساعدة =====
def get_series_list(db_query):
    """جلب قائمة المسلسلات"""
    series = db_query("""
        SELECT 
            series_name,
            COUNT(*) as episode_count,
            MAX(created_at) as last_episode,
            MAX(ep_num) as max_episode
        FROM videos 
        WHERE series_name IS NOT NULL 
            AND series_name != ''
            AND series_name != 'غير معروف'
        GROUP BY series_name
        ORDER BY series_name
    """)
    return series

def get_total_episodes_count(db_query):
    """العدد الإجمالي للحلقات"""
    result = db_query("SELECT COUNT(*) FROM videos")
    return result[0][0] if result else 0

def has_new_episodes(last_episode_date, user_id, series_name):
    """التحقق من وجود حلقة جديدة للمستخدم"""
    if not last_episode_date:
        return False
    
    now = datetime.now()
    if isinstance(last_episode_date, str):
        try:
            last_episode_date = datetime.fromisoformat(last_episode_date)
        except:
            return False
    
    is_new = (now - last_episode_date).total_seconds() < 86400
    
    if not is_new:
        return False
    
    if user_id in user_viewed and series_name in user_viewed[user_id]:
        last_viewed = user_viewed[user_id][series_name]
        if last_viewed > last_episode_date:
            return False
    
    return True

def get_series_button_text(series_name, episode_count, max_episode, last_episode, user_id):
    """تحديد نص الزر"""
    # أولوية: ✅ للمسلسلات المكتملة
    if series_name in completed_series or max_episode >= MAX_EPISODES:
        return f"{series_name} ✅"
    
    # ثم 🆕 للحلقات الجديدة
    if has_new_episodes(last_episode, user_id, series_name):
        return f"{series_name} 🆕"
    
    return series_name

def create_series_keyboard(series_list, bot_username, user_id=None):
    """إنشاء لوحة المفاتيح العادية"""
    keyboard = []
    row = []
    
    for item in series_list:
        if len(item) >= 4:
            series_name = item[0]
            episode_count = item[1]
            last_episode = item[2]
            max_episode = item[3]
        else:
            continue
        
        button_text = get_series_button_text(
            series_name, episode_count, max_episode, last_episode, user_id
        )
        
        button = InlineKeyboardButton(
            button_text,
            callback_data=f"series_{series_name}"
        )
        
        row.append(button)
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    return keyboard

def create_admin_keyboard(series_list, bot_username):
    """إنشاء لوحة المفاتيح للمشرف (مع أزرار الحذف والاكتمال)"""
    keyboard = []
    
    for item in series_list:
        if len(item) >= 4:
            series_name = item[0]
        else:
            continue
        
        # صف واحد لكل مسلسل مع 3 أزرار
        row = [
            InlineKeyboardButton(series_name, callback_data=f"series_{series_name}"),
            InlineKeyboardButton("🗑️", callback_data=f"delete_{series_name}"),
            InlineKeyboardButton("✅", callback_data=f"complete_{series_name}")
        ]
        keyboard.append(row)
    
    # زر العودة للقائمة العادية
    keyboard.append([
        InlineKeyboardButton("🔙 العودة للقائمة العادية", callback_data="back_to_normal")
    ])
    
    return keyboard

# ===== [6] تسجيل المشاهدة =====
def mark_as_viewed(user_id, series_name):
    if user_id not in user_viewed:
        user_viewed[user_id] = {}
    user_viewed[user_id][series_name] = datetime.now()

# ===== [7] دالة التحديث (تحدث فقط عند إضافة حلقة) =====
async def update_series_channel(client, db_query, force=False):
    """تحديث القائمة - فقط عند إضافة حلقة جديدة"""
    global fixed_message_id, last_episode_count
    
    # التحقق من وجود حلقات جديدة
    current_count = get_total_episodes_count(db_query)
    has_new = current_count > last_episode_count
    
    # إذا لم تكن هناك حلقات جديدة وليس force، لا تفعل شيئاً
    if not has_new and not force:
        return
    
    try:
        series_list = get_series_list(db_query)
        if not series_list:
            return
        
        me = await client.get_me()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        text = "📺 **قائمة المسلسلات**\n"
        text += f"🔄 آخر تحديث: {current_time}\n\n"
        text += "🔹 اضغط على أي مسلسل للمشاهدة\n"
        text += "🔹 🆕 = حلقة جديدة (24 ساعة)\n"
        text += "🔹 ✅ = مسلسل مكتمل\n\n"
        
        keyboard = create_series_keyboard(series_list, me.username)
        
        if fixed_message_id:
            try:
                await client.edit_message_text(
                    SERIES_CHANNEL,
                    fixed_message_id,
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logging.info("✅ تم تحديث القائمة")
                return
            except:
                fixed_message_id = None
        
        msg = await client.send_message(
            SERIES_CHANNEL,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        fixed_message_id = msg.id
        logging.info("✅ تم إنشاء قائمة جديدة")
        
        # تحديث العدد الأخير
        last_episode_count = current_count
        
    except Exception as e:
        logging.error(f"❌ خطأ في التحديث: {e}")

# ===== [8] دالة عرض وضع الإدارة =====
async def show_admin_mode(client, callback_query, db_query):
    """عرض القائمة مع أزرار التحكم"""
    series_list = get_series_list(db_query)
    
    if not series_list:
        await callback_query.answer("لا توجد مسلسلات")
        return
    
    me = await client.get_me()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    text = "📺 **وضع الإدارة**\n"
    text += f"🔄 آخر تحديث: {current_time}\n\n"
    text += "🔹 اضغط على اسم المسلسل للمشاهدة\n"
    text += "🔹 🗑️ = حذف المسلسل\n"
    text += "🔹 ✅ = تعيين كمكتمل\n\n"
    
    keyboard = create_admin_keyboard(series_list, me.username)
    
    if fixed_message_id:
        try:
            await client.edit_message_text(
                SERIES_CHANNEL,
                fixed_message_id,
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
    else:
        msg = await client.send_message(
            SERIES_CHANNEL,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        fixed_message_id = msg.id
    
    await callback_query.answer()

# ===== [9] دالة تحديث القائمة (تُستدعى من الملف الرئيسي) =====
async def refresh_series_menu(client, db_query):
    """تُستدعى عند إضافة حلقة جديدة"""
    await update_series_channel(client, db_query, force=True)

# ===== [10] معالجات الأزرار =====
def register_handlers(app, db_query):
    
    @app.on_callback_query(filters.regex(r"^series_"))
    async def handle_series_click(client, callback_query):
        series_name = callback_query.data.replace("series_", "")
        user_id = callback_query.from_user.id
        
        mark_as_viewed(user_id, series_name)
        await callback_query.answer(f"✅ {series_name}", show_alert=False)
    
    @app.on_callback_query(filters.regex(r"^delete_"))
    async def handle_delete(client, callback_query):
        if callback_query.from_user.id != ADMIN_ID:
            await callback_query.answer("⛔ غير مصرح", show_alert=True)
            return
        
        series_name = callback_query.data.replace("delete_", "")
        
        # حذف المسلسل من قاعدة البيانات
        db_query("DELETE FROM videos WHERE series_name = %s", (series_name,), fetch=False)
        
        await callback_query.answer(f"✅ تم حذف {series_name}", show_alert=False)
        
        # العودة لوضع الإدارة بعد الحذف
        await show_admin_mode(client, callback_query, db_query)
    
    @app.on_callback_query(filters.regex(r"^complete_"))
    async def handle_complete(client, callback_query):
        if callback_query.from_user.id != ADMIN_ID:
            await callback_query.answer("⛔ غير مصرح", show_alert=True)
            return
        
        series_name = callback_query.data.replace("complete_", "")
        
        # إضافة المسلسل للمكتملة يدوياً
        completed_series.add(series_name)
        
        await callback_query.answer(f"✅ تم تعيين {series_name} كمكتمل", show_alert=False)
        
        # العودة لوضع الإدارة بعد التعيين
        await show_admin_mode(client, callback_query, db_query)
    
    @app.on_callback_query(filters.regex(r"^back_to_normal$"))
    async def handle_back_to_normal(client, callback_query):
        # العودة للقائمة العادية
        await update_series_channel(client, db_query, force=True)
        await callback_query.answer()

# ===== [11] أوامر المشرف (معدلة للتأكد من العمل) =====
def register_commands(app, db_query):
    
    @app.on_message(filters.command("admin_menu") & filters.private)
    async def admin_menu_cmd(client, message):
        """تفعيل وضع الإدارة - يعمل الآن"""
        
        # التحقق من أن المستخدم هو المشرف
        if message.from_user.id != ADMIN_ID:
            await message.reply_text("⛔ هذا الأمر للمشرف فقط")
            return
        
        series_list = get_series_list(db_query)
        
        if not series_list:
            await message.reply_text("لا توجد مسلسلات")
            return
        
        me = await client.get_me()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        text = "📺 **وضع الإدارة**\n"
        text += f"🔄 آخر تحديث: {current_time}\n\n"
        text += "🔹 اضغط على اسم المسلسل للمشاهدة\n"
        text += "🔹 🗑️ = حذف المسلسل\n"
        text += "🔹 ✅ = تعيين كمكتمل\n\n"
        
        keyboard = create_admin_keyboard(series_list, me.username)
        
        if fixed_message_id:
            try:
                await client.edit_message_text(
                    SERIES_CHANNEL,
                    fixed_message_id,
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                await message.reply_text("✅ تم تفعيل وضع الإدارة")
                return
            except:
                pass
        
        # إذا لم يكن هناك منشور ثابت، أنشئ واحداً جديداً
        msg = await client.send_message(
            SERIES_CHANNEL,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        fixed_message_id = msg.id
        await message.reply_text("✅ تم تفعيل وضع الإدارة")

# ===== [12] دالة التشغيل =====
def setup_series_menu(app, db_query):
    global last_episode_count
    last_episode_count = get_total_episodes_count(db_query)
    
    # تسجيل المعالجات والأوامر
    register_handlers(app, db_query)
    register_commands(app, db_query)
    
    # تحديث مرة واحدة عند التشغيل
    loop = asyncio.get_event_loop()
    loop.create_task(update_series_channel(app, db_query, force=True))
    
    logging.info("✅ تم إعداد قائمة المسلسلات")
