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

def get_total_episodes_count(db_query):
    """الحصول على العدد الإجمالي للحلقات"""
    result = db_query("SELECT COUNT(*) FROM videos")
    return result[0][0] if result else 0

# ===== [4] التحقق من حالة "جديد" للمستخدم =====
def is_new_for_user(series_name, last_date, user_id):
    """التحقق مما إذا كان المسلسل جديداً لهذا المستخدم"""
    if not last_date:
        return False
    
    if isinstance(last_date, str):
        try:
            last_date = datetime.fromisoformat(last_date.replace('Z', '+00:00'))
        except:
            return False
    
    time_diff = datetime.now() - last_date
    is_recent = time_diff.total_seconds() < 86400  # 24 ساعة
    
    if not is_recent:
        return False
    
    if user_id in user_viewed and series_name in user_viewed[user_id]:
        last_viewed = user_viewed[user_id][series_name]
        if last_viewed > last_date:
            return False
    
    return True

# ===== [5] بناء الأزرار الذكية (معدل للقناة) =====
def create_series_keyboard(series_list, bot_username, user_id=None, show_in_channel=False):
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
            # 🔥 للعرض في القناة (يظهر للجميع إذا كانت الحلقة خلال 24 ساعة)
            if show_in_channel:
                if last_date:
                    if isinstance(last_date, str):
                        try:
                            last_date = datetime.fromisoformat(last_date.replace('Z', '+00:00'))
                        except:
                            last_date = None
                    
                    if last_date:
                        time_diff = datetime.now() - last_date
                        if time_diff.total_seconds() < 86400:  # 24 ساعة
                            btn_text += " 🔥"
            else:
                # 🔥 للعرض في الخاص (يظهر فقط لمن لم يشاهد)
                if user_id and is_new_for_user(s_name, last_date, user_id):
                    btn_text += " 🔥"

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
    if user_id not in user_viewed:
        user_viewed[user_id] = {}
    user_viewed[user_id][series_name] = datetime.now()

# ===== [7] دالة التحديث (معدلة للقناة) =====
async def update_series_channel(client, db_query, force=False):
    global fixed_message_id, last_episode_count, bot_info
    
    # التحقق من وجود حلقات جديدة
    current_count = get_total_episodes_count(db_query)
    has_new_episodes = current_count > last_episode_count
    
    # إذا لم تكن هناك حلقات جديدة وليس force، لا تقم بالتحديث
    if not force and not has_new_episodes:
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
    
    # إنشاء النص مع تاريخ التحديث
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"🎬 **مكتبة المسلسلات الحصرية**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔄 آخر تحديث: {update_time}\n\n"
        f"اضغط على اسم المسلسل للمشاهدة الفورية 👇\n\n"
        f"✅ **مسلسل مكتمل**\n"
        f"🔥 **حلقة جديدة (خلال 24 ساعة)**"
    )

    # إنشاء الأزرار مع show_in_channel=True
    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list, bot_info.username, show_in_channel=True))

    try:
        if fixed_message_id:
            try:
                await client.edit_message_text(
                    SERIES_CHANNEL, 
                    fixed_message_id, 
                    text, 
                    reply_markup=reply_markup
                )
                logging.info("✅ تم تحديث قائمة المسلسلات")
            except Exception as e:
                if "MESSAGE_NOT_MODIFIED" in str(e):
                    logging.info("📝 القائمة مطابقة - لا حاجة للتحديث")
                else:
                    raise e
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

# ===== [8] مهمة المراقبة التلقائية =====
async def auto_monitor_task(client, db_query):
    """مهمة دورية للتحقق من وجود حلقات جديدة كل دقيقة"""
    global last_episode_count
    
    while True:
        try:
            current_count = get_total_episodes_count(db_query)
            if current_count > last_episode_count:
                logging.info(f"🆕 اكتشاف {current_count - last_episode_count} حلقة جديدة!")
                await update_series_channel(client, db_query, force=True)
            
            await asyncio.sleep(60)  # فحص كل دقيقة
            
        except Exception as e:
            logging.error(f"❌ خطأ في المراقبة: {e}")
            await asyncio.sleep(60)

# ===== [9] معالج تسجيل المشاهدة =====
def register_handlers(app, db_query):
    
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

    # أمر فحص العدد الحالي
    @app.on_message(filters.command("check_count") & filters.user(ADMIN_ID))
    async def check_count_command(client, message):
        current = get_total_episodes_count(db_query)
        await message.reply_text(f"📊 عدد الحلقات في قاعدة البيانات: {current}\nآخر عدد مسجل: {last_episode_count}")

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

# ===== [10] وظائف الربط =====
def setup_series_menu(app, db_query):
    global last_episode_count
    last_episode_count = get_total_episodes_count(db_query)
    
    register_handlers(app, db_query)
    
    # تشغيل مهمة المراقبة التلقائية
    asyncio.get_event_loop().create_task(auto_monitor_task(app, db_query))
    
    # تحديث أولي
    asyncio.get_event_loop().create_task(update_series_channel(app, db_query, force=True))
    
    logging.info(f"✅ تم إعداد قائمة المسلسلات - العدد الحالي: {last_episode_count}")

async def refresh_series_menu(client, db_query):
    await update_series_channel(client, db_query, force=True)
