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
last_update_time = None
UPDATE_COOLDOWN = 3600  # ساعة كاملة بين التحديثات (3600 ثانية)
MAX_EPISODES = 30

# ===== [3] تخزين حالة المشاهدة =====
user_viewed = {}
completed_series = set()

# ===== [4] متغير لمنع التحديثات غير الضرورية =====
last_episode_count = 0
update_in_progress = False  # لمنع التحديثات المتزامنة

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
    """الحصول على العدد الإجمالي للحلقات"""
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
    if series_name in completed_series or max_episode >= MAX_EPISODES:
        return f"{series_name} ✅"
    
    if has_new_episodes(last_episode, user_id, series_name):
        return f"{series_name} 🆕"
    
    return series_name

def create_series_keyboard(series_list, bot_username, user_id=None, show_controls=False):
    """إنشاء لوحة المفاتيح"""
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
    
    if show_controls:
        keyboard.append([
            InlineKeyboardButton("🔄 تحديث يدوي", callback_data="manual_update"),
            InlineKeyboardButton("⚙️ إدارة", callback_data="show_admin_menu")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("🔄 تحديث يدوي", callback_data="manual_update")
        ])
    
    return keyboard

# ===== [6] تسجيل المشاهدة =====
def mark_as_viewed(user_id, series_name):
    if user_id not in user_viewed:
        user_viewed[user_id] = {}
    user_viewed[user_id][series_name] = datetime.now()

# ===== [7] دالة التحديث (معدلة لمنع التكرار) =====
async def update_series_channel(client, db_query, user_id=None, force=False):
    """تحديث القائمة - مرة واحدة فقط عند الحاجة"""
    global fixed_message_id, last_update_time, last_episode_count, update_in_progress
    
    # منع التحديثات المتزامنة
    if update_in_progress:
        logging.info("⏳ تحديث قيد التنفيذ بالفعل - تخطي")
        return
    
    # التحقق من وجود حلقات جديدة (مرة كل ساعة فقط)
    current_count = get_total_episodes_count(db_query)
    has_new_episode = current_count > last_episode_count
    
    # إذا لم تكن هناك حلقات جديدة وليس force، لا تقم بالتحديث
    if not force and not has_new_episode and last_update_time:
        time_since_last = (datetime.now() - last_update_time).total_seconds()
        if time_since_last < UPDATE_COOLDOWN:
            logging.info(f"⏳ لا توجد حلقات جديدة - تخطي التحديث")
            return
    
    update_in_progress = True
    
    try:
        series_list = get_series_list(db_query)
        if not series_list:
            logging.warning("⚠️ لا توجد مسلسلات")
            update_in_progress = False
            return
        
        me = await client.get_me()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        text = "📺 **قائمة المسلسلات**\n"
        text += f"🔄 آخر تحديث: {current_time}\n\n"
        text += "🔹 اضغط على أي مسلسل للمشاهدة\n"
        text += "🔹 🆕 = حلقة جديدة (24 ساعة)\n"
        text += "🔹 ✅ = مسلسل مكتمل\n\n"
        
        keyboard = create_series_keyboard(series_list, me.username, user_id, False)
        
        if fixed_message_id:
            try:
                await client.edit_message_text(
                    SERIES_CHANNEL,
                    fixed_message_id,
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logging.info("✅ تم تحديث القائمة")
            except Exception as e:
                logging.warning(f"⚠️ فشل تحديث المنشور القديم: {e}")
                fixed_message_id = None
        
        if not fixed_message_id:
            msg = await client.send_message(
                SERIES_CHANNEL,
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            fixed_message_id = msg.id
            logging.info("✅ تم إنشاء قائمة جديدة")
        
        last_update_time = datetime.now()
        last_episode_count = current_count
        
    except Exception as e:
        logging.error(f"❌ خطأ في التحديث: {e}")
    finally:
        update_in_progress = False

# ===== [8] معالجات الأزرار =====
def register_handlers(app, db_query):
    
    @app.on_callback_query(filters.regex(r"^series_"))
    async def handle_series_click(client, callback_query):
        series_name = callback_query.data.replace("series_", "")
        user_id = callback_query.from_user.id
        
        mark_as_viewed(user_id, series_name)
        await callback_query.answer(f"✅ {series_name}", show_alert=False)
    
    @app.on_callback_query(filters.regex(r"^manual_update$"))
    async def handle_manual_update(client, callback_query):
        if callback_query.from_user.id != ADMIN_ID:
            await callback_query.answer("⛔ غير مصرح", show_alert=True)
            return
        
        await callback_query.answer("🔄 جاري التحديث...", show_alert=False)
        await update_series_channel(client, db_query, force=True)
    
    @app.on_callback_query(filters.regex(r"^show_admin_menu$"))
    async def handle_show_admin(client, callback_query):
        if callback_query.from_user.id != ADMIN_ID:
            await callback_query.answer("⛔ غير مصرح", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("🗑️ حذف مسلسل", callback_data="admin_delete")],
            [InlineKeyboardButton("✅ تعيين كمكتمل", callback_data="admin_complete")],
            [InlineKeyboardButton("❌ إلغاء الاكتمال", callback_data="admin_incomplete")],
            [InlineKeyboardButton("🔙 عودة", callback_data="back_to_normal")]
        ]
        
        await callback_query.message.edit_text(
            "⚙️ **لوحة التحكم**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await callback_query.answer()
    
    @app.on_callback_query(filters.regex(r"^back_to_normal$"))
    async def handle_back_to_normal(client, callback_query):
        await update_series_channel(client, db_query, force=True)
    
    @app.on_callback_query(filters.regex(r"^admin_delete$"))
    async def handle_admin_delete(client, callback_query):
        series_list = get_series_list(db_query)
        keyboard = []
        row = []
        
        for item in series_list:
            series_name = item[0]
            button = InlineKeyboardButton(f"🗑️ {series_name}", callback_data=f"delete_{series_name}")
            row.append(button)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="show_admin_menu")])
        
        await callback_query.message.edit_text(
            "📋 **اختر المسلسل للحذف**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await callback_query.answer()
    
    @app.on_callback_query(filters.regex(r"^delete_"))
    async def handle_delete(client, callback_query):
        series_name = callback_query.data.replace("delete_", "")
        db_query("DELETE FROM videos WHERE series_name = %s", (series_name,), fetch=False)
        await callback_query.message.edit_text(f"✅ تم حذف {series_name}")
        await callback_query.answer()
        await update_series_channel(app, db_query, force=True)
    
    # أوامر المشرف
    @app.on_message(filters.command("admin_menu") & filters.user(ADMIN_ID))
    async def admin_menu_cmd(client, message):
        await update_series_channel(client, db_query, force=True)
        await message.reply_text("✅ تم تفعيل وضع الإدارة")

# ===== [9] دالة التشغيل =====
def setup_series_menu(app, db_query):
    global last_episode_count
    last_episode_count = get_total_episodes_count(db_query)
    register_handlers(app, db_query)
    loop = asyncio.get_event_loop()
    loop.create_task(update_series_channel(app, db_query, force=True))
    logging.info("✅ تم إعداد قائمة المسلسلات")
