# ===== series_menu.py =====
import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003894735143
UPDATE_INTERVAL = 3600
ADMIN_ID = 7720165591

# ===== [2] دوال مساعدة =====
def get_series_list(db_query):
    """جلب قائمة المسلسلات (بدون last_episode مؤقتاً)"""
    
    series = db_query("""
        SELECT 
            series_name,
            COUNT(*) as episode_count
        FROM videos 
        WHERE series_name IS NOT NULL 
            AND series_name != ''
            AND series_name != 'غير معروف'
        GROUP BY series_name
        ORDER BY series_name
    """)
    
    return series

def create_series_keyboard(series_list, bot_username):
    """إنشاء لوحة مفاتيح المسلسلات"""
    
    keyboard = []
    row = []
    
    for item in series_list:
        series_name = item[0]
        
        button = InlineKeyboardButton(
            series_name,
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
        InlineKeyboardButton("🔙 العودة", callback_data="back_to_menu")
    ])
    
    await callback_query.message.edit_text(
        f"📺 **{series_name}**\nاختر الحلقة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await callback_query.answer()

async def update_series_channel(client, db_query):
    """إنشاء قائمة المسلسلات"""
    
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
        
        # محاولة إرسال رسالة جديدة (أسهل من البحث عن القديمة)
        await client.send_message(
            SERIES_CHANNEL,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logging.info("✅ تم إنشاء قائمة المسلسلات")
        
    except Exception as e:
        logging.error(f"❌ خطأ: {e}")

async def auto_update_task(client, db_query):
    """تحديث تلقائي"""
    while True:
        try:
            await update_series_channel(client, db_query)
            await asyncio.sleep(UPDATE_INTERVAL)
        except Exception as e:
            logging.error(f"❌ خطأ: {e}")
            await asyncio.sleep(60)

def register_handlers(app, db_query):
    """تسجيل معالجات الأزرار"""
    
    @app.on_callback_query(filters.regex(r"^series_"))
    async def handle_series_click(client, callback_query):
        series_name = callback_query.data.replace("series_", "")
        await show_series_episodes(client, callback_query, series_name, db_query)
    
    @app.on_callback_query(filters.regex(r"^back_to_menu$"))
    async def handle_back_to_menu(client, callback_query):
        await callback_query.message.delete()
        await update_series_channel(client, db_query)
    
    @app.on_callback_query(filters.regex(r"^refresh_series_menu$"))
    async def handle_refresh_menu(client, callback_query):
        await callback_query.answer("🔄 جاري التحديث...")
        await update_series_channel(client, db_query)
        await callback_query.message.delete()

def register_commands(app, db_query):
    """تسجيل أوامر التحكم"""
    
    @app.on_message(filters.command("update_menu") & filters.user(ADMIN_ID))
    async def update_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري التحديث...")
        await update_series_channel(client, db_query)
        await msg.edit_text("✅ تم التحديث")
    
    @app.on_message(filters.command("refresh_menu") & filters.user(ADMIN_ID))
    async def refresh_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري الإنشاء...")
        await update_series_channel(client, db_query)
        await msg.edit_text("✅ تم الإنشاء")

def setup_series_menu(app, db_query):
    """تشغيل النظام"""
    register_handlers(app, db_query)
    register_commands(app, db_query)
    loop = asyncio.get_event_loop()
    loop.create_task(auto_update_task(app, db_query))
    loop.create_task(update_series_channel(app, db_query))
    logging.info("✅ تم إعداد قائمة المسلسلات")
