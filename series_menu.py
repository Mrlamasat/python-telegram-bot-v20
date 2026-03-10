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
# هيكل: {user_id: {series_name: last_viewed_timestamp}}
user_viewed = {}

# ===== [4] دوال مساعدة =====
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

def is_completed(episode_count, max_episode):
    """التحقق مما إذا كان المسلسل مكتملاً"""
    return max_episode >= MAX_EPISODES

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
    if is_completed(episode_count, max_episode):
        return f"{series_name} ✅"
    
    # التحقق من وجود حلقات جديدة
    if has_new_episodes(last_episode, user_id, series_name):
        return f"{series_name} 🆕"
    
    return series_name

def create_series_keyboard(series_list, bot_username, user_id=None):
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
    control_row = [
        InlineKeyboardButton("🔄 تحديث", callback_data="refresh_series_menu")
    ]
    
    keyboard.append(control_row)
    
    return keyboard

# ===== [5] تسجيل المشاهدة =====
def mark_as_viewed(user_id, series_name):
    """تسجيل أن المستخدم شاهد المسلسل"""
    if user_id not in user_viewed:
        user_viewed[user_id] = {}
    user_viewed[user_id][series_name] = datetime.now()

# ===== [6] دالة التحديث =====
async def update_series_channel(client, db_query, user_id=None, force=False):
    """تحديث المنشور الثابت في القناة"""
    global fixed_message_id, last_update_time
    
    # منع التحديث المتكرر
    if not force and last_update_time:
        time_since_last = (datetime.now() - last_update_time).total_seconds()
        if time_since_last < UPDATE_COOLDOWN:
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
        text += "🔹 🆕 = حلقة جديدة (24 ساعة)\n"
        text += "🔹 ✅ = مسلسل مكتمل\n\n"
        
        keyboard = create_series_keyboard(series_list, me.username, user_id)
        
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
                fixed_message_id = None
        
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

# ===== [7] دالة تحديث القائمة (تُستدعى من الملف الرئيسي) =====
async def refresh_series_menu(client, db_query):
    """تحديث القائمة عند إضافة حلقة جديدة"""
    await update_series_channel(client, db_query, force=True)

# ===== [8] معالجات الأزرار =====
def register_handlers(app, db_query):
    
    @app.on_callback_query(filters.regex(r"^series_"))
    async def handle_series_click(client, callback_query):
        series_name = callback_query.data.replace("series_", "")
        user_id = callback_query.from_user.id
        
        # تسجيل أن المستخدم شاهد هذا المسلسل
        mark_as_viewed(user_id, series_name)
        
        # تحديث القائمة للمستخدم (تختفي 🆕)
        await update_series_channel(client, db_query, user_id=user_id, force=True)
        
        # إرسال رسالة ترحيب
        await callback_query.message.reply_text(
            f"🎬 **{series_name}**\n"
            f"يمكنك مشاهدة الحلقات عبر البوت:\n"
            f"اضغط على الرابط: @{app.me.username}"
        )
        
        await callback_query.answer(f"تم اختيار {series_name}")
    
    @app.on_callback_query(filters.regex(r"^refresh_series_menu$"))
    async def handle_refresh_menu(client, callback_query):
        await callback_query.answer("🔄 جاري تحديث القائمة...")
        await update_series_channel(client, db_query, force=True)
        await callback_query.message.delete()
    
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
        completed = 0
        new = 0
        
        for item in series_list:
            if len(item) >= 4:
                _, count, last_ep, max_ep = item
                if max_ep >= MAX_EPISODES:
                    completed += 1
                if last_ep and (datetime.now() - last_ep).total_seconds() < 86400:
                    new += 1
        
        text = f"📊 **إحصائيات القائمة**\n\n"
        text += f"📁 إجمالي المسلسلات: {total}\n"
        text += f"✅ مسلسلات مكتملة: {completed}\n"
        text += f"🆕 مسلسلات جديدة: {new}\n"
        text += f"🔄 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        await message.reply_text(text)

# ===== [9] دالة التشغيل =====
def setup_series_menu(app, db_query):
    """تشغيل النظام"""
    register_handlers(app, db_query)
    # تحديث واحد فقط عند التشغيل
    loop = asyncio.get_event_loop()
    loop.create_task(update_series_channel(app, db_query, force=True))
    logging.info("✅ تم إعداد قائمة المسلسلات الثابتة")
