# ===== series_menu.py =====
# ملف مستقل لإدارة قائمة المسلسلات في القناة الخاصة
# يتم استدعاؤه من الملف الرئيسي

import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003894735143  # قناة المسلسلات الخاصة
UPDATE_INTERVAL = 3600  # التحديث كل ساعة (بالثواني)

# ===== [2] دوال مساعدة =====
def get_series_list(db_query):
    """جلب قائمة المسلسلات مع آخر حلقة لكل منها"""
    
    # جلب جميع المسلسلات مع عدد حلقاتها وآخر تحديث
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
    time_diff = now - last_episode_date
    return time_diff.total_seconds() < 86400  # 24 ساعة

def create_series_keyboard(series_list, bot_username):
    """إنشاء لوحة مفاتيح المسلسلات (3-4 أزرار في كل سطر)"""
    
    keyboard = []
    row = []
    
    for series_name, episode_count, last_episode in series_list:
        # التحقق من وجود حلقة جديدة
        is_new = check_new_episodes(last_episode)
        
        # إضافة علامة 🆕 إذا كان هناك حلقة جديدة
        button_text = f"{series_name} 🆕" if is_new else series_name
        
        # إنشاء زر للمسلسل
        button = InlineKeyboardButton(
            button_text,
            callback_data=f"series_{series_name}"
        )
        
        row.append(button)
        
        # 3 أزرار في كل سطر (يمكن تغييرها إلى 4)
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    # إضافة الصف الأخير إذا كان فيه أزرار
    if row:
        keyboard.append(row)
    
    # إضافة زر التحديث اليدوي
    keyboard.append([
        InlineKeyboardButton("🔄 تحديث القائمة", callback_data="refresh_series_menu")
    ])
    
    return keyboard

# ===== [3] دوال التفاعل مع المسلسلات =====
async def show_series_episodes(client, callback_query, series_name, db_query):
    """عرض حلقات مسلسل معين"""
    
    # جلب حلقات المسلسل
    episodes = db_query("""
        SELECT ep_num, v_id FROM videos 
        WHERE series_name = %s 
        ORDER BY ep_num ASC 
        LIMIT 50
    """, (series_name,))
    
    if not episodes:
        await callback_query.answer("لا توجد حلقات لهذا المسلسل")
        return
    
    # بناء أزرار الحلقات
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
    
    # زر العودة للقائمة الرئيسية
    keyboard.append([
        InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
    ])
    
    await callback_query.message.edit_text(
        f"📺 **{series_name}**\nاختر رقم الحلقة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== [4] إنشاء/تحديث منشور القائمة =====
async def update_series_channel(client, db_query):
    """إنشاء أو تحديث منشور قائمة المسلسلات في القناة"""
    
    # جلب قائمة المسلسلات
    series_list = get_series_list(db_query)
    
    if not series_list:
        logging.warning("⚠️ لا توجد مسلسلات لعرضها")
        return
    
    # إنشاء نص القائمة
    me = await client.get_me()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    text = "📺 **قائمة المسلسلات**\n"
    text += f"🔄 آخر تحديث: {current_time}\n\n"
    
    # إنشاء لوحة المفاتيح
    keyboard = create_series_keyboard(series_list, me.username)
    
    # البحث عن منشور قديم في القناة
    async for message in client.get_chat_history(SERIES_CHANNEL, limit=10):
        if message.text and "📺 **قائمة المسلسلات**" in message.text:
            # تحديث المنشور القديم
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            logging.info("✅ تم تحديث قائمة المسلسلات")
            return
    
    # إذا لم يوجد منشور قديم، إنشاء واحد جديد
    await client.send_message(
        SERIES_CHANNEL,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    logging.info("✅ تم إنشاء قائمة المسلسلات الجديدة")

# ===== [5] مهمة التحديث التلقائي =====
async def auto_update_task(client, db_query):
    """مهمة دورية لتحديث القائمة كل ساعة"""
    while True:
        try:
            await update_series_channel(client, db_query)
            await asyncio.sleep(UPDATE_INTERVAL)
        except Exception as e:
            logging.error(f"❌ خطأ في التحديث التلقائي: {e}")
            await asyncio.sleep(60)  # انتظر دقيقة ثم حاول مجدداً

# ===== [6] معالج الأزرار =====
def register_handlers(app, db_query):
    """تسجيل معالجات الأزرار الخاصة بقائمة المسلسلات"""
    
    @app.on_callback_query(filters.regex(r"^series_"))
    async def handle_series_click(client, callback_query):
        series_name = callback_query.data.replace("series_", "")
        await show_series_episodes(client, callback_query, series_name, db_query)
    
    @app.on_callback_query(filters.regex(r"^back_to_menu$"))
    async def handle_back_to_menu(client, callback_query):
        # العودة للقائمة الرئيسية
        series_list = get_series_list(db_query)
        me = await client.get_me()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        text = "📺 **قائمة المسلسلات**\n"
        text += f"🔄 آخر تحديث: {current_time}\n\n"
        
        keyboard = create_series_keyboard(series_list, me.username)
        
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @app.on_callback_query(filters.regex(r"^refresh_series_menu$"))
    async def handle_refresh_menu(client, callback_query):
        await callback_query.answer("🔄 جاري تحديث القائمة...")
        await update_series_channel(client, db_query)
        await callback_query.message.delete()

# ===== [7] أوامر التحكم عبر البوت =====
def register_commands(app, db_query):
    """تسجيل أوامر التحكم في قائمة المسلسلات"""
    
    @app.on_message(filters.command("update_menu") & filters.user(ADMIN_ID))
    async def update_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري تحديث قائمة المسلسلات...")
        await update_series_channel(client, db_query)
        await msg.edit_text("✅ تم تحديث قائمة المسلسلات بنجاح")
    
    @app.on_message(filters.command("refresh_menu") & filters.user(ADMIN_ID))
    async def refresh_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري إعادة إنشاء القائمة...")
        
        # حذف جميع منشورات القائمة القديمة
        async for msg in client.get_chat_history(SERIES_CHANNEL, limit=20):
            if msg.text and "📺 **قائمة المسلسلات**" in msg.text:
                await msg.delete()
        
        # إنشاء قائمة جديدة
        await update_series_channel(client, db_query)
        await msg.edit_text("✅ تم إعادة إنشاء القائمة بنجاح")
    
    @app.on_message(filters.command("menu_stats") & filters.user(ADMIN_ID))
    async def menu_stats_command(client, message):
        series_list = get_series_list(db_query)
        
        # حساب الإحصائيات
        total_series = len(series_list)
        new_series = 0
        
        for _, _, last_ep in series_list:
            if check_new_episodes(last_ep):
                new_series += 1
        
        text = f"📊 **إحصائيات قائمة المسلسلات**\n\n"
        text += f"📁 إجمالي المسلسلات: {total_series}\n"
        text += f"🆕 مسلسلات بحلقات جديدة: {new_series}\n"
        text += f"🔄 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        text += f"⏱ تحديث تلقائي كل ساعة"
        
        await message.reply_text(text)

# ===== [8] دالة التشغيل الرئيسية =====
def setup_series_menu(app, db_query):
    """إعداد وتشغيل نظام قائمة المسلسلات"""
    
    # تسجيل المعالجات
    register_handlers(app, db_query)
    register_commands(app, db_query)
    
    # تشغيل مهمة التحديث التلقائي
    loop = asyncio.get_event_loop()
    loop.create_task(auto_update_task(app, db_query))
    
    # تحديث القائمة فوراً عند التشغيل
    loop.create_task(update_series_channel(app, db_query))
    
    logging.info("✅ تم إعداد نظام قائمة المسلسلات")
