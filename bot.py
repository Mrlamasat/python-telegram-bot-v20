import os
import psycopg2
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية (محفوظة كما هي) =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_stable", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_check_state = {}

# ===== قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=10)
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"Database Error: {e}")
        return []

def init_database():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            ep_num INTEGER,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            last_view TIMESTAMP
        )
    """, fetch=False)

# ===== دوال المساعدة والتشفير =====
def encrypt_title(title, level=2):
    if not title: return "مسلسل"
    title = title.strip()
    if len(title) <= 4: return title[:2] + "••"
    if level == 3:
        first = title[0]
        last = title[-1]
        middle = len(title[1:-1].replace(" ", ""))
        return f"{first}••{middle}••{last}"
    return title[:2] + "•••" + title[-2:]

def format_duration(seconds):
    if not seconds: return "غير معروف"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours > 0 else f"{minutes}:{secs:02d}"

async def is_valid_video(client, v_id):
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        return msg and not msg.empty
    except: return False

async def get_video_info(client, v_id):
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if msg and msg.video:
            v = msg.video
            q = "Full HD" if v.height >= 1080 else "HD" if v.height >= 720 else "SD" if v.height >= 480 else "منخفضة"
            return {"duration": format_duration(v.duration), "quality": q, "size": f"{v.file_size/(1024*1024):.1f} MB", "height": v.height, "width": v.width}
    except: return None

# ===== [النظام الذكي المطور] جلب الحلقات مع التحقق المزدوج والتنظيف الآلي =====
async def get_episodes_markup(client, title, current_v_id):
    # جلب كافة الإدخالات لهذا المسلسل مرتبة تصاعدياً برقم الحلقة وتنازلياً بالمعرف (الأحدث أولاً)
    all_entries = db_query("""
        SELECT v_id, ep_num 
        FROM videos 
        WHERE title = %s AND status = 'posted' 
        ORDER BY ep_num ASC, CAST(v_id AS INTEGER) DESC
    """, (title,))
    
    valid_episodes = {} # سنخزن فيه {رقم_الحلقة: معرف_الفيديو_الشغال}
    
    for v_id, ep_num in all_entries:
        # إذا كنا قد وجدنا نسخة شغالة لهذه الحلقة مسبقاً، نتخطى القديم
        if ep_num in valid_episodes:
            continue
            
        # التحقق الفوري: هل الفيديو موجود في القناة؟
        if await is_valid_video(client, v_id):
            valid_episodes[ep_num] = v_id
        else:
            # تنظيف تلقائي: الفيديو محذوف؟ احذفه من قاعدة البيانات فوراً
            logging.info(f"Auto-cleaning deleted video: {v_id}")
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)

    keyboard = []
    row = []
    # ترتيب الحلقات المفلترة للعرض
    sorted_eps = sorted(valid_episodes.items()) 
    
    for ep_num, v_id in sorted_eps:
        # تمييز الحلقة التي يشاهدها المستخدم الآن
        btn_text = f"• {ep_num} •" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{v_id}"))
        
        if len(row) == 5:
            keyboard.append(row)
            row = []
            
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("📢 قناة النشر الاحتياطية", url=BACKUP_CHANNEL_LINK)])
    return InlineKeyboardMarkup(keyboard)

# ===== وظيفة عرض الحلقة التفاعلية =====
async def show_episode(client, message, current_vid, is_callback=False):
    video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not video_info:
        if is_callback: await message.answer("⚠️ هذه الحلقة لم تعد متوفرة", show_alert=True)
        else: await message.reply_text("⚠️ هذه الحلقة غير موجودة")
        return

    title, current_ep = video_info[0]
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    info = await get_video_info(client, current_vid)
    encrypted_title = encrypt_title(title, level=3)
    
    caption = (
        f"<b>📺 {encrypted_title}</b>\n"
        f"<b>🎬 الحلقة رقم: {current_ep}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
    )
    if info:
        caption += f"⏱️ المدة: {info['duration']} | 📊 الجودة: {info['quality']}\n"
        caption += f"💾 الحجم: {info['size']}\n"
    
    caption += f"\n🍿 **انتقل بين الحلقات المتوفرة:**"
    
    # استدعاء نظام الأزرار الذكي (مع await و Client)
    reply_markup = await get_episodes_markup(client, title, current_vid)

    try:
        if is_callback:
            # حذف الرسالة القديمة وإرسال الفيديو الجديد لضمان تحديث المحتوى المرئي
            await message.delete()
        
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(current_vid),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Display Error: {e}")

# ===== معالجات الرسائل والأزرار =====

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        await show_episode(client, message, v_id)
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📢 القناة الإحتياطية", url=BACKUP_CHANNEL_LINK)]])
        await message.reply_text(f"👋 أهلاً بك يا محمد في بوت المسلسلات!\nاختر حلقة من القناة للمشاهدة.", reply_markup=markup)

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data.startswith("go_"):
        target_vid = data.split("_")[1]
        await callback_query.answer("جاري الانتقال...")
        await show_episode(client, callback_query.message, target_vid, is_callback=True)
        return

    # معالجات الإدارة (Check & Verify)
    try:
        if data == "start_check":
            if user_id != ADMIN_ID: return
            if user_id in user_check_state and user_check_state[user_id]:
                await callback_query.message.delete()
                await show_next_for_check(client, callback_query.message, user_id)
        elif data.startswith("verify_"):
            action, v_id = data.split("_")[1], data.split("_")[2]
            if action == "delete": db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            if user_id in user_check_state:
                user_check_state[user_id] = [i for i in user_check_state[user_id] if i[0] != v_id]
                await callback_query.message.delete()
                await show_next_for_check(client, callback_query.message, user_id)
    except: pass

# ===== معالج قناة المصدر (نظام النشر) =====

@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        if message.video or message.document:
            v_id = str(message.id)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO NOTHING", (v_id,), fetch=False)
            await message.reply_text(f"✅ تم استلام الفيديو `{v_id}`\nأرسل البوستر الآن.")
        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption or "مسلسل", message.photo.file_id, res[0][0]), fetch=False)
                await message.reply_text("📌 تم حفظ البوستر. أرسل رقم الحلقة الآن.")
        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id, title, p_id = res[0]
                db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (int(message.text), v_id), fetch=False)
                me = await app.get_me()
                pub_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
                await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{encrypt_title(title)}</b>\n<b>الحلقة: [{message.text}]</b>", reply_markup=pub_markup)
                await message.reply_text(f"✅ تم النشر: {title} - حلقة {message.text}")
    except Exception as e: logging.error(f"Source Error: {e}")

# ===== وظائف الإدارة الباقية =====
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    views = db_query("SELECT SUM(views) FROM videos")[0][0] or 0
    await message.reply_text(f"📊 إحصائيات النظام:\n• إجمالي الحلقات: {total}\n• إجمالي المشاهدات: {views:,}")

@app.on_message(filters.command("fix") & filters.private)
async def fix_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    status_msg = await message.reply_text("🔍 جاري تنظيف الروابط المعطلة...")
    all_vids = db_query("SELECT v_id FROM videos WHERE status = 'posted'")
    deleted = 0
    for (v_id,) in all_vids:
        if not await is_valid_video(client, v_id):
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            deleted += 1
    await status_msg.edit_text(f"✅ تم التنظيف!\nتم حذف {deleted} رابط معطل.")

async def show_next_for_check(client, message, user_id):
    if user_id not in user_check_state or not user_check_state[user_id]:
        await client.send_message(user_id, "✅ انتهى الفحص.")
        return
    v_id, title, ep_num = user_check_state[user_id][0]
    btns = [[InlineKeyboardButton("✅ سليم", callback_data=f"verify_confirm_{v_id}"), InlineKeyboardButton("🗑️ حذف", callback_data=f"verify_delete_{v_id}")]]
    await client.copy_message(user_id, SOURCE_CHANNEL, int(v_id), caption=f"فحص: {title} - {ep_num}", reply_markup=InlineKeyboardMarkup(btns))

if __name__ == "__main__":
    init_database()
    logging.info("🚀 البوت انطلق بنظام التنظيف الذكي!")
    app.run()
