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
UPDATE_COOLDOWN = 60  # ثانية بين التحديثات
MAX_EPISODES = 30  # الحد الأقصى لعدد حلقات المسلسل

# ===== [3] تخزين حالة المشاهدة للمستخدمين =====
user_viewed = {}

# ===== [4] تخزين المسلسلات المكتملة يدوياً =====
# هذا جدول افتراضي - يمكن تخزينه في قاعدة البيانات لاحقاً
completed_series = set()  # مسلسلات مكتملة يدوياً

# ===== [5] دوال مساعدة =====
def get_series_list(db_query):
    """جلب قائمة المسلسلات مع معلومات كاملة"""
    
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

def is_completed(series_name, episode_count, max_episode):
    """التحقق مما إذا كان المسلسل مكتملاً"""
    # مكتمل يدوياً أو وصل للحد الأقصى
    return series_name in completed_series or max_episode >= MAX_EPISODES

def has_new_episodes(last_episode_date, user_id, series_name):
    """التحقق مما إذا كانت هناك حلقة جديدة للمستخدم"""
    if not last_episode_date:
        return False
    
    now = datetime.now()
    if isinstance(last_episode_date, str):
        try:
            last_episode_date = datetime.fromisoformat(last_episode_date)
        except:
            return False
    
    # التحقق من أن الحلقة خلال آخر 24 ساعة
    is_new = (now - last_episode_date).total_seconds() < 86400
    
    if not is_new:
        return False
    
    # التحقق مما إذا كان المستخدم قد شاهد الحلقة
    if user_id in user_viewed and series_name in user_viewed[user_id]:
        last_viewed = user_viewed[user_id][series_name]
        # إذا شاهد الحلقة بعد نزولها، لا تظهر 🆕
        if last_viewed > last_episode_date:
            return False
    
    return True

def get_series_button_text(series_name, episode_count, max_episode, last_episode, user_id):
    """تحديد نص الزر بناءً على حالة المسلسل والمستخدم"""
    
    # التحقق من الاكتمال
    if is_completed(series_name, episode_count, max_episode):
        return f"{series_name} ✅"
    
    # التحقق من وجود حلقات جديدة
    if has_new_episodes(last_episode, user_id, series_name):
        return f"{series_name} 🆕"
    
    return series_name

def create_series_keyboard(series_list, bot_username, user_id=None, show_controls=False):
    """إنشاء لوحة مفاتيح المسلسلات"""
    
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
    
    # أزرار التحكم
    if show_controls:
        control_row = [
            InlineKeyboardButton("🔄 تحديث", callback_data="refresh_series_menu"),
            InlineKeyboardButton("⚙️ إدارة", callback_data="show_admin_menu")
        ]
        keyboard.append(control_row)
    else:
        keyboard.append([
            InlineKeyboardButton("🔄 تحديث القائمة", callback_data="refresh_series_menu")
        ])
    
    return keyboard

# ===== [6] تسجيل المشاهدة =====
def mark_as_viewed(user_id, series_name):
    """تسجيل أن المستخدم شاهد المسلسل"""
    if user_id not in user_viewed:
        user_viewed[user_id] = {}
    user_viewed[user_id][series_name] = datetime.now()

# ===== [7] دالة التحديث =====
async def update_series_channel(client, db_query, user_id=None, force=False, show_controls=False):
    """تحديث المنشور الثابت في القناة"""
    global fixed_message_id, last_update_time
    
    # منع التحديث المتكرر
    if not force and last_update_time:
        time_since_last = (datetime.now() - last_update_time).total_seconds()
        if time_since_last < UPDATE_COOLDOWN:
            logging.info(f"⏳ تم تجاهل التحديث - آخر تحديث منذ {time_since_last:.0f} ثانية")
            return
    
    try:
        series_list = get_series_list(db_query)
        
        if not series_list:
            logging.warning("⚠️ لا توجد مسلسلات")
            return
        
        me = await client.get_me()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        text = "📺 **قائمة المسلسلات**\n"
        text += f"🔄 آخر تحديث: {current_time}\n\n"
        text += "🔹 اضغط على أي مسلسل للمشاهدة\n"
        text += "🔹 🆕 = حلقة جديدة (24 ساعة)\n"
        text += "🔹 ✅ = مسلسل مكتمل\n\n"
        
        keyboard = create_series_keyboard(series_list, me.username, user_id, show_controls)
        
        if fixed_message_id:
            try:
                await client.edit_message_text(
                    SERIES_CHANNEL,
                    fixed_message_id,
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                last_update_time = datetime.now()
                logging.info("✅ تم تحديث القائمة")
                return
            except Exception as e:
                logging.warning(f"⚠️ فشل تحديث المنشور القديم: {e}")
        
        # إنشاء منشور جديد
        msg = await client.send_message(
            SERIES_CHANNEL,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        fixed_message_id = msg.id
        last_update_time = datetime.now()
        logging.info("✅ تم إنشاء قائمة جديدة")
        
    except Exception as e:
        logging.error(f"❌ خطأ في التحديث: {e}")

# ===== [8] دوال الإدارة =====
async def show_admin_menu(client, callback_query, db_query):
    """عرض قائمة الإدارة"""
    
    keyboard = [
        [InlineKeyboardButton("🗑️ حذف مسلسل", callback_data="admin_delete")],
        [InlineKeyboardButton("✅ تعيين كمكتمل", callback_data="admin_complete")],
        [InlineKeyboardButton("❌ إلغاء الاكتمال", callback_data="admin_incomplete")],
        [InlineKeyboardButton("🔙 العودة", callback_data="back_to_menu")]
    ]
    
    await callback_query.message.edit_text(
        "⚙️ **لوحة التحكم**\n\nاختر ما تريد فعله:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await callback_query.answer()

async def show_series_list_for_action(client, callback_query, db_query, action):
    """عرض قائمة المسلسلات لإجراء معين"""
    
    series_list = get_series_list(db_query)
    
    if not series_list:
        await callback_query.answer("لا توجد مسلسلات")
        return
    
    keyboard = []
    row = []
    
    for item in series_list:
        series_name = item[0]
        
        if action == "delete":
            button_text = f"🗑️ {series_name}"
            callback = f"delete_{series_name}"
        elif action == "complete":
            button_text = f"✅ {series_name}"
            callback = f"complete_{series_name}"
        elif action == "incomplete":
            button_text = f"❌ {series_name}"
            callback = f"incomplete_{series_name}"
        
        button = InlineKeyboardButton(button_text, callback_data=callback)
        row.append(button)
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="show_admin_menu")])
    
    await callback_query.message.edit_text(
        f"📋 **اختر المسلسل**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await callback_query.answer()

# ===== [9] دالة تحديث القائمة =====
async def refresh_series_menu(client, db_query):
    """تحديث القائمة عند إضافة حلقة جديدة"""
    await update_series_channel(client, db_query, force=True)

# ===== [10] معالجات الأزرار =====
def register_handlers(app, db_query):
    
    @app.on_callback_query(filters.regex(r"^series_"))
    async def handle_series_click(client, callback_query):
        series_name = callback_query.data.replace("series_", "")
        user_id = callback_query.from_user.id
        
        mark_as_viewed(user_id, series_name)
        await update_series_channel(client, db_query, user_id=user_id, force=True)
        await callback_query.answer(f"✅ {series_name}", show_alert=False)
    
    @app.on_callback_query(filters.regex(r"^refresh_series_menu$"))
    async def handle_refresh_menu(client, callback_query):
        await callback_query.answer("🔄 جاري التحديث...", show_alert=False)
        await update_series_channel(client, db_query, force=True)
    
    @app.on_callback_query(filters.regex(r"^show_admin_menu$"))
    async def handle_show_admin(client, callback_query):
        await show_admin_menu(client, callback_query, db_query)
    
    @app.on_callback_query(filters.regex(r"^back_to_menu$"))
    async def handle_back_to_menu(client, callback_query):
        await update_series_channel(client, db_query, force=True, show_controls=True)
        await callback_query.message.delete()
    
    @app.on_callback_query(filters.regex(r"^admin_delete$"))
    async def handle_admin_delete(client, callback_query):
        await show_series_list_for_action(client, callback_query, db_query, "delete")
    
    @app.on_callback_query(filters.regex(r"^admin_complete$"))
    async def handle_admin_complete(client, callback_query):
        await show_series_list_for_action(client, callback_query, db_query, "complete")
    
    @app.on_callback_query(filters.regex(r"^admin_incomplete$"))
    async def handle_admin_incomplete(client, callback_query):
        await show_series_list_for_action(client, callback_query, db_query, "incomplete")
    
    @app.on_callback_query(filters.regex(r"^delete_"))
    async def handle_delete_series(client, callback_query):
        series_name = callback_query.data.replace("delete_", "")
        
        # حذف المسلسل من قاعدة البيانات
        db_query("DELETE FROM videos WHERE series_name = %s", (series_name,), fetch=False)
        
        await callback_query.message.edit_text(f"✅ تم حذف مسلسل {series_name}")
        await callback_query.answer()
        
        # تحديث القائمة
        await update_series_channel(app, db_query, force=True, show_controls=True)
    
    @app.on_callback_query(filters.regex(r"^complete_"))
    async def handle_complete_series(client, callback_query):
        series_name = callback_query.data.replace("complete_", "")
        
        # إضافة المسلسل إلى قائمة المكتملة يدوياً
        completed_series.add(series_name)
        
        await callback_query.message.edit_text(f"✅ تم تعيين {series_name} كمكتمل")
        await callback_query.answer()
        
        # تحديث القائمة
        await update_series_channel(app, db_query, force=True, show_controls=True)
    
    @app.on_callback_query(filters.regex(r"^incomplete_"))
    async def handle_incomplete_series(client, callback_query):
        series_name = callback_query.data.replace("incomplete_", "")
        
        # إزالة المسلسل من قائمة المكتملة يدوياً
        if series_name in completed_series:
            completed_series.remove(series_name)
        
        await callback_query.message.edit_text(f"✅ تم إلغاء الاكتمال لـ {series_name}")
        await callback_query.answer()
        
        # تحديث القائمة
        await update_series_channel(app, db_query, force=True, show_controls=True)
    
    # أوامر المشرف
    @app.on_message(filters.command("admin_menu") & filters.user(ADMIN_ID))
    async def admin_menu_command(client, message):
        await update_series_channel(client, db_query, force=True, show_controls=True)
        await message.reply_text("✅ تم تفعيل أزرار التحكم في القائمة")
    
    @app.on_message(filters.command("update_menu") & filters.user(ADMIN_ID))
    async def update_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري تحديث القائمة...")
        await update_series_channel(client, db_query, force=True)
        await msg.edit_text("✅ تم تحديث القائمة")
    
    @app.on_message(filters.command("refresh_menu") & filters.user(ADMIN_ID))
    async def refresh_menu_command(client, message):
        global fixed_message_id
        fixed_message_id = None
        msg = await message.reply_text("🔄 جاري إنشاء القائمة...")
        await update_series_channel(client, db_query, force=True)
        await msg.edit_text("✅ تم إنشاء القائمة")
    
    @app.on_message(filters.command("menu_stats") & filters.user(ADMIN_ID))
    async def menu_stats_command(client, message):
        series_list = get_series_list(db_query)
        
        total = len(series_list)
        completed = len(completed_series)
        new = 0
        
        for item in series_list:
            if len(item) >= 4:
                _, _, last_ep, _ = item
                if last_ep and (datetime.now() - last_ep).total_seconds() < 86400:
                    new += 1
        
        text = f"📊 **إحصائيات القائمة**\n\n"
        text += f"📁 إجمالي المسلسلات: {total}\n"
        text += f"✅ مكتملة يدوياً: {completed}\n"
        text += f"🆕 مسلسلات جديدة: {new}\n"
        text += f"🔄 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        await message.reply_text(text)

# ===== [11] دالة التشغيل =====
def setup_series_menu(app, db_query):
    """تشغيل النظام"""
    register_handlers(app, db_query)
    loop = asyncio.get_event_loop()
    loop.create_task(update_series_channel(app, db_query, force=True))
    logging.info("✅ تم إعداد قائمة المسلسلات الثابتة")
