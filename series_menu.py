import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import SERIES_CHANNEL, SOURCE_CHANNEL, ADMIN_ID, MAX_EPISODES
from config import FORCE_SUB_LINK  # نفس رابط الاشتراك الإجباري
from database import db_query
from force_sub import get_backup_channel_button

# ===== متغيرات التخزين =====
fixed_message_id = None
user_viewed = {}
completed_series = set()  
last_episode_count = 0
bot_info = None 

# ===== جلب البيانات =====
def get_series_list():
    return db_query("""
        SELECT 
            s.series_name,
            COUNT(*) as episode_count,
            MAX(s.created_at) as last_episode_date,
            MAX(s.ep_num) as max_episode,
            MIN(s.ep_num) as min_episode,
            (SELECT v_id FROM videos WHERE series_name = s.series_name ORDER BY ep_num DESC LIMIT 1) as last_v_id,
            (SELECT v_id FROM videos WHERE series_name = s.series_name ORDER BY ep_num ASC LIMIT 1) as first_v_id
        FROM videos s
        WHERE s.series_name IS NOT NULL AND s.series_name != ''
        GROUP BY s.series_name
        ORDER BY s.series_name
    """)

def get_total_episodes_count():
    result = db_query("SELECT COUNT(*) FROM videos")
    return result[0][0] if result else 0

def is_new_for_user(series_name, last_date, user_id):
    if not last_date: return False
    if isinstance(last_date, str):
        try:
            last_date = datetime.fromisoformat(last_date.replace('Z', '+00:00'))
        except:
            return False
    time_diff = datetime.now() - last_date
    is_recent = time_diff.total_seconds() < 86400
    if not is_recent: return False
    if user_id in user_viewed and series_name in user_viewed[user_id]:
        last_viewed = user_viewed[user_id][series_name]
        if last_viewed > last_date: return False
    return True

def create_series_keyboard(series_list, bot_username, user_id=None, show_in_channel=False):
    keyboard = []
    row = []
    for item in series_list:
        if len(item) < 7: continue
        s_name, count, last_date, max_ep, min_ep, last_v_id, first_v_id = item
        if not last_v_id or not first_v_id: continue
        
        btn_text = s_name
        is_completed = s_name in completed_series or (max_ep and max_ep >= 30)
        
        if is_completed:
            btn_text += " ✅"
        else:
            if show_in_channel:
                if last_date:
                    if isinstance(last_date, str):
                        try:
                            last_date = datetime.fromisoformat(last_date.replace('Z', '+00:00'))
                        except:
                            last_date = None
                    if last_date:
                        time_diff = datetime.now() - last_date
                        if time_diff.total_seconds() < 86400:
                            btn_text += " 🔥"
            else:
                if user_id and is_new_for_user(s_name, last_date, user_id):
                    btn_text += " 🔥"

        target_v_id = first_v_id if is_completed else last_v_id
        direct_url = f"https://t.me/{bot_username}?start={target_v_id}"
        row.append(InlineKeyboardButton(btn_text, url=direct_url))
        
        if len(row) == 3: 
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return keyboard

async def update_series_channel(client, force=False):
    global fixed_message_id, last_episode_count, bot_info
    current_count = get_total_episodes_count()
    has_new_episodes = current_count > last_episode_count
    if not force and not has_new_episodes: return

    if not bot_info: bot_info = await client.get_me()
    series_list = get_series_list()
    if not series_list: return
    
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"🎬 **مكتبة المسلسلات الحصرية**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔄 آخر تحديث: {update_time}\n\n"
        f"اضغط على اسم المسلسل للمشاهدة الفورية 👇\n\n"
        f"✅ **مسلسل مكتمل (ينتقل للحلقة الأولى)**\n"
        f"🔥 **حلقة جديدة (خلال 24 ساعة)**"
    )
    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list, bot_info.username, show_in_channel=True))

    try:
        if fixed_message_id:
            try:
                await client.edit_message_text(SERIES_CHANNEL, fixed_message_id, text, reply_markup=reply_markup)
                logging.info("✅ تم تحديث قائمة المسلسلات")
            except Exception as e:
                if "MESSAGE_NOT_MODIFIED" in str(e):
                    logging.info("📝 القائمة مطابقة - لا حاجة للتحديث")
                else:
                    raise e
        else:
            msg = await client.send_message(SERIES_CHANNEL, text, reply_markup=reply_markup)
            fixed_message_id = msg.id
            logging.info("✅ تم إنشاء قائمة المسلسلات")
        last_episode_count = current_count
    except Exception as e:
        logging.error(f"❌ خطأ في تحديث القائمة: {e}")

async def auto_monitor_task(client):
    global last_episode_count
    while True:
        try:
            current_count = get_total_episodes_count()
            if current_count > last_episode_count:
                logging.info(f"🆕 اكتشاف {current_count - last_episode_count} حلقة جديدة!")
                await update_series_channel(client, force=True)
            await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"❌ خطأ في المراقبة: {e}")
            await asyncio.sleep(60)

def register_handlers(app):
    
    @app.on_message(filters.command("update_series_menu") & filters.user(ADMIN_ID))
    async def update_series_menu_command(client, message):
        msg = await message.reply_text("🔄 جاري تحديث قائمة المسلسلات...")
        await update_series_channel(client, force=True)
        await msg.edit_text("✅ تم تحديث قائمة المسلسلات")

    @app.on_message(filters.command("refresh_series_menu") & filters.user(ADMIN_ID))
    async def refresh_series_menu_command(client, message):
        global fixed_message_id
        fixed_message_id = None
        msg = await message.reply_text("🔄 جاري إنشاء قائمة المسلسلات من جديد...")
        await update_series_channel(client, force=True)
        await msg.edit_text("✅ تم إنشاء قائمة المسلسلات")

    @app.on_message(filters.command("check_count") & filters.user(ADMIN_ID))
    async def check_count_command(client, message):
        current = get_total_episodes_count()
        await message.reply_text(f"📊 عدد الحلقات في قاعدة البيانات: {current}\nآخر عدد مسجل: {last_episode_count}")

    @app.on_message(filters.command("admin_menu") & filters.user(ADMIN_ID))
    async def show_admin(client, message):
        series_list = get_series_list()
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
        
        await update_series_channel(client, force=True)

def setup_series_menu(app):
    global last_episode_count
    last_episode_count = get_total_episodes_count()
    register_handlers(app)
    asyncio.get_event_loop().create_task(auto_monitor_task(app))
    asyncio.get_event_loop().create_task(update_series_channel(app, force=True))
    logging.info(f"✅ تم إعداد قائمة المسلسلات - العدد الحالي: {last_episode_count}")

async def refresh_series_menu(client):
    await update_series_channel(client, force=True)
