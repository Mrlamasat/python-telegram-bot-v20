# ===== series_menu.py =====
import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003894735143
ADMIN_ID = 7720165591

# ===== [2] متغير لتخزين معرف المنشور الثابت =====
fixed_message_id = None

# ===== [3] دوال مساعدة =====
def get_series_list(db_query):
    """جلب قائمة المسلسلات مع آخر حلقة لكل منها"""
    
    series = db_query("""
        SELECT 
            series_name,
            COUNT(*) as episode_count,
            MAX(created_at) as last_episode
        FROM videos 
        WHERE series_name IS NOT NULL 
            AND series_name != ''
            AND series_name != 'غير معروف'
        GROUP BY series_name
        ORDER BY series_name
    """)
    
    return series

def check_new_episodes(last_episode_date):
    """التحقق مما إذا كانت هناك حلقة جديدة خلال آخر 24 ساعة"""
    if not last_episode_date:
        return False
    
    now = datetime.now()
    if isinstance(last_episode_date, str):
        try:
            last_episode_date = datetime.fromisoformat(last_episode_date)
        except:
            return False
    
    time_diff = now - last_episode_date
    return time_diff.total_seconds() < 86400  # 24 ساعة

def create_series_keyboard(series_list, bot_username):
    """إنشاء لوحة مفاتيح المسلسلات مع أيقونة NEW"""
    
    keyboard = []
    row = []
    
    for item in series_list:
        if len(item) >= 3:
            series_name = item[0]
            last_episode = item[2]
        else:
            continue
        
        is_new = check_new_episodes(last_episode)
        button_text = f"{series_name} 🆕" if is_new else series_name
        
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
    
    keyboard.append([
        InlineKeyboardButton("🔄 تحديث القائمة", callback_data="refresh_series_menu")
    ])
    
    return keyboard

async def show_series_episodes(client, callback_query, series_name, db_query):
    """عرض حلقات مسلسل معين"""
    
    episodes = db_query("""
        SELECT ep_num, v_id FROM videos 
        WHERE series_name = %s 
        ORDER BY ep_num ASC 
        LIMIT 50
    """, (series_name,))
    
    if not episodes:
        await callback_query.answer("لا توجد حلقات")
        return
    
    keyboard = []
    row = []
    me = await client.get_me()
    
    for ep_num, v_id in episodes:
        row.append(InlineKeyboardButton(
            str(ep_num),
            url=f"https://t.me/{me.username}?start={v_id}"
        ))
        
        if len(row) == 5:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([
        InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
    ])
    
    await callback_query.message.edit_text(
        f"📺 **{series_name}**\nاختر رقم الحلقة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await callback_query.answer()

# ===== [4] دالة التحديث (بدون استخدام get_chat_history) =====
async def update_series_channel(client, db_query):
    """إنشاء أو تحديث المنشور الثابت في القناة"""
    global fixed_message_id
    
    try:
        series_list = get_series_list(db_query)
        
        if not series_list:
            logging.warning("⚠️ لا توجد مسلسلات")
            return
        
        me = await client.get_me()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        text = "📺 **قائمة المسلسلات**\n"
        text += f"🔄 آخر تحديث: {current_time}\n\n"
        
        keyboard = create_series_keyboard(series_list, me.username)
        
        # إذا كان لدينا معرف منشور سابق، نقوم بتحديثه
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
        logging.info("✅ تم إنشاء قائمة جديدة")
        
    except Exception as e:
        logging.error(f"❌ خطأ في التحديث: {e}")

# ===== [5] دالة عامة للتحديث =====
async def refresh_series_menu(client, db_query):
    """دالة يمكن استدعاؤها من الملف الرئيسي"""
    await update_series_channel(client, db_query)

# ===== [6] معالجات الأزرار =====
def register_handlers(app, db_query):
    
    @app.on_callback_query(filters.regex(r"^series_"))
    async def handle_series_click(client, callback_query):
        series_name = callback_query.data.replace("series_", "")
        await show_series_episodes(client, callback_query, series_name, db_query)
    
    @app.on_callback_query(filters.regex(r"^back_to_menu$"))
    async def handle_back_to_menu(client, callback_query):
        await update_series_channel(client, db_query)
        await callback_query.message.delete()
        await callback_query.answer()
    
    @app.on_callback_query(filters.regex(r"^refresh_series_menu$"))
    async def handle_refresh_menu(client, callback_query):
        await callback_query.answer("🔄 جاري التحديث...")
        await update_series_channel(client, db_query)
        await callback_query.message.delete()
    
    @app.on_message(filters.command("update_menu") & filters.user(ADMIN_ID))
    async def update_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري تحديث القائمة...")
        await update_series_channel(client, db_query)
        await msg.edit_text("✅ تم تحديث القائمة")
    
    @app.on_message(filters.command("refresh_menu") & filters.user(ADMIN_ID))
    async def refresh_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري إنشاء القائمة...")
        await update_series_channel(client, db_query)
        await msg.edit_text("✅ تم إنشاء القائمة")
    
    @app.on_message(filters.command("menu_stats") & filters.user(ADMIN_ID))
    async def menu_stats_command(client, message):
        series_list = get_series_list(db_query)
        
        total = len(series_list)
        new_count = 0
        
        for item in series_list:
            if len(item) >= 3 and check_new_episodes(item[2]):
                new_count += 1
        
        text = f"📊 **إحصائيات القائمة**\n\n"
        text += f"📁 إجمالي المسلسلات: {total}\n"
        text += f"🆕 مسلسلات جديدة: {new_count}\n"
        text += f"🔄 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        await message.reply_text(text)

# ===== [7] دالة التشغيل الرئيسية =====
def setup_series_menu(app, db_query):
    """تشغيل النظام"""
    register_handlers(app, db_query)
    loop = asyncio.get_event_loop()
    loop.create_task(update_series_channel(app, db_query))
    logging.info("✅ تم إعداد قائمة المسلسلات الثابتة")
