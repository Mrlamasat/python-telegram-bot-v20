import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003227314572
SOURCE_CHANNEL = -1003547072209
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
            (SELECT v_id FROM videos WHERE series_name = s.series_name ORDER BY created_at DESC LIMIT 1) as last_v_id
        FROM videos s
        WHERE s.series_name IS NOT NULL AND s.series_name != ''
        GROUP BY s.series_name
        ORDER BY s.series_name
    """)

# ===== [4] التحقق من حالة "جديد" للمستخدم =====
def is_new_for_user(series_name, last_date, user_id):
    """التحقق مما إذا كان المسلسل جديداً لهذا المستخدم"""
    if not last_date:
        return False
    
    # تحويل النص إلى تاريخ إذا لزم الأمر
    if isinstance(last_date, str):
        try:
            last_date = datetime.fromisoformat(last_date.replace('Z', '+00:00'))
        except:
            return False
    
    # التحقق من أن الحلقة خلال آخر 24 ساعة
    time_diff = datetime.now() - last_date
    is_recent = time_diff.total_seconds() < 86400  # 24 ساعة
    
    if not is_recent:
        return False
    
    # التحقق مما إذا كان المستخدم قد شاهد بالفعل
    if user_id in user_viewed and series_name in user_viewed[user_id]:
        last_viewed = user_viewed[user_id][series_name]
        if last_viewed > last_date:
            return False  # شاهدها بعد نزولها
    
    return True  # جديدة ولم يشاهدها

# ===== [5] بناء الأزرار الذكية =====
def create_series_keyboard(series_list, bot_username, user_id=None):
    keyboard = []
    row = []
    
    for item in series_list:
        if len(item) < 5:
            continue
            
        s_name = item[0]
        count = item[1]
        last_date = item[2]
        max_ep = item[3]
        last_v_id = item[4]
        
        if not last_v_id:
            continue
        
        btn_text = s_name
        
        # ✅ المسلسلات المكتملة
        if s_name in completed_series or (max_ep and max_ep >= MAX_EPISODES):
            btn_text += " ✅"
        else:
            # 🔥 فقط إذا كان جديداً ولم يشاهده هذا المستخدم
            if user_id and is_new_for_user(s_name, last_date, user_id):
                btn_text += " 🔥"

        # الرابط المباشر للبوت
        direct_url = f"https://t.me/{bot_username}?start={last_v_id}"
        row.append(InlineKeyboardButton(btn_text, url=direct_url))
        
        if len(row) == 3: 
            keyboard.append(row)
            row = []
    
    if row: 
        keyboard.append(row)
    
    return keyboard

# ===== [6] تسجيل المشاهدة =====
async def record_view(user_id, series_name, v_id, db_query):
    """تسجيل أن المستخدم شاهد المسلسل"""
    if user_id not in user_viewed:
        user_viewed[user_id] = {}
    user_viewed[user_id][series_name] = datetime.now()

# ===== [7] التحديث التلقائي للقناة =====
async def update_series_channel(client, db_query, force=False):
    global fixed_message_id, last_episode_count, bot_info
    
    # التحقق من وجود حلقات جديدة
    res = db_query("SELECT COUNT(*) FROM videos")
    current_count = res[0][0] if res else 0
    
    # إذا لم تكن هناك حلقات جديدة وليس force، لا تقم بالتحديث
    if not force and current_count <= last_episode_count:
        logging.info("⏳ لا توجد حلقات جديدة - تخطي التحديث")
        return

    # جلب معلومات البوت
    if not bot_info:
        bot_info = await client.get_me()

    # جلب قائمة المسلسلات
    series_list = get_series_list(db_query)
    if not series_list:
        logging.warning("⚠️ لا توجد مسلسلات لعرضها")
        return
    
    # إنشاء النص
    text = (
        "🎬 **مكتبة المسلسلات الحصرية**\n"
        "━━━━━━━━━━━━━━━\n"
        "اضغط على اسم المسلسل للمشاهدة الفورية 👇\n\n"
        "✅ **مسلسل مكتمل**\n"
        "🔥 **يظهر فقط لمن لم يشاهد الحلقة الجديدة (خلال 24 ساعة)**"
    )

    # إنشاء الأزرار (بدون user_id للعرض العام)
    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list, bot_info.username))

    try:
        if fixed_message_id:
            await client.edit_message_text(
                SERIES_CHANNEL, 
                fixed_message_id, 
                text, 
                reply_markup=reply_markup
            )
            logging.info("✅ تم تحديث قائمة المسلسلات")
        else:
            msg = await client.send_message(
                SERIES_CHANNEL, 
                text, 
                reply_markup=reply_markup
            )
            fixed_message_id = msg.id
            logging.info("✅ تم إنشاء قائمة المسلسلات")
        
        # تحديث العدد الأخير
        last_episode_count = current_count
        
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث القائمة: {e}")

# ===== [8] معالج تسجيل المشاهدة =====
def register_handlers(app, db_query):
    
    # تسجيل المشاهدة عند فتح الرابط
    @app.on_message(filters.command("start") & filters.private)
    async def track_start(client, message):
        user_id = message.from_user.id
        args = message.command
        
        if len(args) > 1:
            v_id = args[1]
            res = db_query("SELECT series_name FROM videos WHERE v_id = %s", (v_id,))
            if res:
                s_name = res[0][0]
                await record_view(user_id, s_name, v_id, db_query)

    # أمر تحديث قائمة المسلسلات
    @app.on_message(filters.command("update_series_menu") & filters.user(ADMIN_ID))
    async def update_series_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري تحديث قائمة المسلسلات...")
        await update_series_channel(client, db_query, force=True)
        await msg.edit_text("✅ تم تحديث قائمة المسلسلات")

    # أمر إعادة إنشاء القائمة
    @app.on_message(filters.command("refresh_series_menu") & filters.user(ADMIN_ID))
    async def refresh_series_menu_command(client, message):
        global fixed_message_id
        fixed_message_id = None
        msg = await message.reply_text("🔄 جاري إنشاء قائمة المسلسلات من جديد...")
        await update_series_channel(client, db_query, force=True)
        await msg.edit_text("✅ تم إنشاء قائمة المسلسلات")

    # لوحة الإدارة
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

# ===== [9] وظائف الربط =====
def setup_series_menu(app, db_query):
    register_handlers(app, db_query)
    asyncio.get_event_loop().create_task(update_series_channel(app, db_query, force=True))

async def refresh_series_menu(client, db_query):
    await update_series_channel(client, db_query, force=True)
