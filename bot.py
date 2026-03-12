import os, psycopg2, logging, re, asyncio, time, random
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserNotParticipant

# استيراد دوال التحديث
from series_menu import refresh_series_menu

logging.basicConfig(level=logging.INFO)

# ===== # ===== [1] الإعدادات من متغيرات البيئة =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = int(os.environ.get("SOURCE_CHANNEL", "-1003547072209"))
PUBLISH_CHANNEL = int(os.environ.get("PUBLISH_CHANNEL", "-1003689965691"))
FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "-1003637472584"))

ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+pTT0n-NtJ7ZiMWZk"

# ===== [1.1] التحكم في المزيد من الحلقات =====
SHOW_MORE_BUTTONS = True

# ===== [1.2] نظام الحماية من FloodWait =====
user_last_request = {}
REQUEST_LIMIT = 5
TIME_WINDOW = 10

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دوال التحقق من الاشتراك =====
async def check_force_sub(client, user_id):
    """التحقق من اشتراك المستخدم في القناة الإجبارية"""
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception as e:
        logging.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

async def get_force_sub_button():
    """الحصول على زر الاشتراك في القناة"""
    try:
        chat = await app.get_chat(FORCE_SUB_CHANNEL)
        chat_link = chat.invite_link or f"https://t.me/{chat.username}" if chat.username else "https://t.me/+..."
        return InlineKeyboardButton("🔔 اشترك في القناة أولاً", url=chat_link)
    except:
        return InlineKeyboardButton("🔔 اشترك في القناة", url="https://t.me/...")

# ===== [3] كلمات عشوائية للتشفير =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد"]

def encrypt_title(title):
    if not title: return "محتوى"
    words = title.split()
    if words:
        word = random.choice(words)
        return f"🎬 {word[::-1]} {random.randint(10,99)}"
    return f"🎬 {random.choice(ENCRYPTION_WORDS)} {random.randint(10,99)}"

# ===== [4] دالة قاعدة البيانات =====
def db_query(query, params=(), fetch=True, retry=3):
    for attempt in range(retry):
        try:
            conn = psycopg2.connect(DATABASE_URL, sslmode="require")
            cur = conn.cursor()
            cur.execute(query, params)
            res = cur.fetchall() if fetch else None
            conn.commit()
            cur.close()
            conn.close()
            return res
        except Exception as e:
            logging.error(f"DB Error (attempt {attempt+1}): {e}")
            if attempt == retry - 1:
                return [] if fetch else None
            time.sleep(1)

# ===== [5] إنشاء الجداول =====
def init_database():
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, series_name TEXT, ep_num INTEGER DEFAULT 0, quality TEXT DEFAULT 'HD', views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS posters (poster_id BIGINT PRIMARY KEY, series_name TEXT, video_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT, first_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS pending_posts (video_id TEXT PRIMARY KEY, step TEXT, poster_id BIGINT, quality TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS views_log (id SERIAL PRIMARY KEY, v_id TEXT, viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    print("✅ قاعدة البيانات جاهزة")

# ===== [6] دوال الاستخراج =====
def extract_series_name(text):
    if not text: return None
    text = text.strip()
    patterns = [
        r'^(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$',
        r'^(.+?)\s+(\d+)$',
        r'^(.+?)\s*-\s*(\d+)$',
        r'^(.+?)\s*[\[\(\{]\d+[\]\)\}]',
        r'^(.+?)\s+.*?\s+(\d+)$',
        r'^مسلسل\s+(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$',
        r'^مسلسل\s+(.+?)\s+(\d+)$',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'[-\s]+$', '', name)
            name = re.sub(r'[\[\(\{].*$', '', name)
            return name
    return text.strip()

def extract_episode_number(text):
    if not text: return 0
    text = text.strip()
    match = re.search(r'(?:حلقة|حلقه|الحلقة|الحلقه)\s*[:\-]?\s*(\d+)', text, re.IGNORECASE)
    if match: return int(match.group(1))
    match = re.search(r'[\[\(\{](\d+)[\]\)\}]', text)
    if match: return int(match.group(1))
    match = re.search(r'-\s*(\d+)\s*$', text)
    if match: return int(match.group(1))
    nums = re.findall(r'\d+', text)
    if nums: return int(nums[-1])
    return 0

# ===== [7] دالة جلب بيانات الحلقة =====
async def get_video_data_from_source(client, v_id):
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not msg or not msg.video:
            return None, None, None
        caption = msg.caption or ""
        series_name = extract_series_name(caption)
        ep_num = extract_episode_number(caption)
        if not series_name: series_name = f"مسلسل {v_id[-3:]}"
        if ep_num == 0: ep_num = 1
        db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, 'HD') ON CONFLICT (v_id) DO UPDATE SET series_name = EXCLUDED.series_name, ep_num = EXCLUDED.ep_num", (v_id, series_name, ep_num), fetch=False)
        logging.info(f"🔄 تحديث تلقائي {v_id}: {series_name} - حلقة {ep_num}")
        return series_name, ep_num, "HD"
    except Exception as e:
        logging.error(f"❌ خطأ في جلب بيانات {v_id}: {e}")
        return None, None, None

# ===== [8] متابعة التعديلات على الفيديوهات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def on_video_edit(client, message):
    try:
        v_id = str(message.id)
        caption = message.caption or ""
        series_name = extract_series_name(caption)
        ep_num = extract_episode_number(caption)
        if series_name and ep_num > 0:
            db_query("UPDATE videos SET series_name = %s, ep_num = %s WHERE v_id = %s", (series_name, ep_num, v_id), fetch=False)
            logging.info(f"✏️ تحديث يدوي {v_id}: {series_name} - حلقة {ep_num}")
            await client.send_message(ADMIN_ID, f"🔄 **تم تحديث حلقة**\nالمعرف: {v_id}\nالمسلسل: {series_name}\nرقم الحلقة: {ep_num}")
            await refresh_series_menu(client, db_query)
    except Exception as e:
        logging.error(f"Error in on_video_edit: {e}")

# ===== [9] متابعة التعديلات على البوسترات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def on_poster_edit(client, message):
    try:
        poster_id = message.id
        new_series = extract_series_name(message.caption or "")
        if new_series:
            db_query("UPDATE posters SET series_name = %s WHERE poster_id = %s", (new_series, poster_id), fetch=False)
            video = db_query("SELECT video_id FROM posters WHERE poster_id = %s", (poster_id,))
            if video and video[0][0]:
                db_query("UPDATE videos SET series_name = %s WHERE v_id = %s", (new_series, video[0][0]), fetch=False)
                logging.info(f"✏️ تحديث بوستر {poster_id} → {new_series}")
                await refresh_series_menu(client, db_query)
    except Exception as e:
        logging.error(f"Error in on_poster_edit: {e}")

# ===== [10] مراقبة قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.photo))
async def monitor_source(client, message):
    try:
        if message.video:
            v_id = str(message.id)
            caption = message.caption or ""
            series_name = extract_series_name(caption)
            ep_num = extract_episode_number(caption)
            if series_name and ep_num > 0:
                db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, 'HD') ON CONFLICT (v_id) DO UPDATE SET series_name = EXCLUDED.series_name, ep_num = EXCLUDED.ep_num", (v_id, series_name, ep_num), fetch=False)
                logging.info(f"✅ فيديو مكتمل {v_id}: {series_name} - حلقة {ep_num}")
                await refresh_series_menu(client, db_query)
                try:
                    encrypted = encrypt_title(series_name)
                    me = await client.get_me()
                    btn = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
                    ]])
                    caption_publish = f"🎬 **{encrypted}**\n🔢 **الحلقة {ep_num}**\n📺 **الجودة HD**"
                    await client.copy_message(PUBLISH_CHANNEL, SOURCE_CHANNEL, int(v_id), caption=caption_publish, reply_markup=btn)
                    await message.reply_text(f"✅ تم النشر في القناة العامة: {series_name} - حلقة {ep_num}")
                except Exception as e:
                    logging.error(f"❌ فشل النشر: {e}")
                    await message.reply_text(f"✅ تم حفظ الفيديو: {series_name} - حلقة {ep_num}\n⚠️ لكن فشل النشر في القناة العامة: {e}")
            else:
                db_query("INSERT INTO pending_posts (video_id, step) VALUES (%s, 'waiting_for_poster') ON CONFLICT (video_id) DO UPDATE SET step = 'waiting_for_poster'", (v_id,), fetch=False)
                await message.reply_text(f"📹 تم استلام الفيديو ({v_id})\nارفع البوستر الآن مع اسم المسلسل في الوصف.")
        elif message.photo:
            poster_id = message.id
            s_name = extract_series_name(message.caption or "")
            if not s_name:
                await message.reply_text("⚠️ اكتب اسم المسلسل في وصف البوستر!")
                return
            pending = db_query("SELECT video_id FROM pending_posts WHERE step = 'waiting_for_poster' ORDER BY created_at DESC LIMIT 1")
            if pending:
                video_id = pending[0][0]
                db_query("INSERT INTO posters (poster_id, series_name, video_id) VALUES (%s, %s, %s)", (poster_id, s_name, video_id), fetch=False)
                db_query("UPDATE pending_posts SET step = 'waiting_for_quality', poster_id = %s WHERE video_id = %s", (poster_id, video_id), fetch=False)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("HD", callback_data=f"q_HD_{video_id}"),
                    InlineKeyboardButton("SD", callback_data=f"q_SD_{video_id}"),
                    InlineKeyboardButton("4K", callback_data=f"q_4K_{video_id}")
                ]])
                await message.reply_text(f"🖼 تم ربط {s_name}\nاختر الجودة:", reply_markup=kb)
    except Exception as e: 
        logging.error(f"Error in monitor_source: {e}")

# ===== [11] معالجة الجودة =====
@app.on_callback_query(filters.regex(r"^q_"))
async def handle_quality(client, cb):
    try:
        _, quality, v_id = cb.data.split('_')
        db_query("UPDATE pending_posts SET step = 'waiting_for_episode', quality = %s WHERE video_id = %s", (quality, v_id), fetch=False)
        await cb.message.edit_text(f"📊 الجودة: {quality}\nأرسل رقم الحلقة الآن.")
    except Exception as e:
        logging.error(f"Error in handle_quality: {e}")

# ===== [12] استقبال رقم الحلقة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.regex(r"^/"))
async def receive_episode(client, message):
    try:
        ep_num = extract_episode_number(message.text)
        if ep_num == 0: 
            await message.reply_text("❌ لم أتمكن من قراءة رقم الحلقة. أرسل رقماً فقط مثل: 5")
            return
        pending = db_query("SELECT video_id, poster_id, quality FROM pending_posts WHERE step = 'waiting_for_episode' ORDER BY created_at DESC LIMIT 1")
        if not pending:
            await message.reply_text("❌ لا يوجد طلب معلق. ابدأ برفع فيديو أولاً")
            return
        v_id, p_id, q = pending[0]
        poster_data = db_query("SELECT series_name FROM posters WHERE poster_id = %s", (p_id,))
        if not poster_data:
            await message.reply_text("❌ لم يتم العثور على البوستر")
            return
        s_name = poster_data[0][0]
        db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, %s)", (v_id, s_name, ep_num, q), fetch=False)
        db_query("DELETE FROM pending_posts WHERE video_id = %s", (v_id,), fetch=False)
        await refresh_series_menu(client, db_query)
        try:
            encrypted = encrypt_title(s_name)
            me = await client.get_me()
            btn = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
            ]])
            caption = f"🎬 **{encrypted}**\n🔢 **الحلقة {ep_num}**\n📺 **الجودة {q}**"
            await client.copy_message(PUBLISH_CHANNEL, SOURCE_CHANNEL, int(p_id), caption=caption, reply_markup=btn)
            logging.info(f"✅ تم النشر في القناة العامة: {s_name} - حلقة {ep_num}")
            await message.reply_text(f"✅ تم النشر في القناة العامة: {s_name} - حلقة {ep_num}")
        except Exception as e: 
            logging.error(f"❌ فشل النشر: {e}")
            await message.reply_text(f"❌ فشل النشر في القناة العامة. تأكد أن البوت مشرف في القناة.\nالخطأ: {e}")
    except Exception as e:
        logging.error(f"Error in receive_episode: {e}")
        await message.reply_text(f"❌ حدث خطأ: {e}")

# ===== [13] نظام الحماية من FloodWait =====
def check_rate_limit(user_id):
    now = datetime.now()
    if user_id in user_last_request:
        user_last_request[user_id] = [t for t in user_last_request[user_id] if now - t < timedelta(seconds=TIME_WINDOW)]
    else:
        user_last_request[user_id] = []
    if len(user_last_request[user_id]) >= REQUEST_LIMIT:
        oldest = user_last_request[user_id][0]
        wait_time = TIME_WINDOW - (now - oldest).seconds
        return False, wait_time
    user_last_request[user_id].append(now)
    return True, 0

# ===== [14] أمر البدء مع الاشتراك الإجباري =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    
    # التحقق من الاشتراك الإجباري
    is_subscribed = await check_force_sub(client, user_id)
    if not is_subscribed:
        force_btn = await get_force_sub_button()
        keyboard = InlineKeyboardMarkup([[force_btn]])
        await message.reply_text(
            "🔒 **عذراً، يجب الاشتراك في القناة أولاً**\n\n"
            "للتمكن من مشاهدة الحلقات، الرجاء الاشتراك في القناة ثم أعد المحاولة.",
            reply_markup=keyboard
        )
        return
    
    allowed, wait_time = check_rate_limit(user_id)
    if not allowed:
        await message.reply_text(f"⏳ أنت تطلب بسرعة! انتظر {wait_time} ثانية")
        return
    
    try:
        db_query("INSERT INTO users (user_id, username, first_name, last_used) VALUES (%s, %s, %s, CURRENT_TIMESTAMP) ON CONFLICT (user_id) DO UPDATE SET last_used = CURRENT_TIMESTAMP", 
                 (user_id, message.from_user.username or "", message.from_user.first_name or ""), fetch=False)
    except:
        pass
    
    if len(message.command) > 1:
        v_id = message.command[1]
        data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        if not data:
            series_name, ep_num, quality = await get_video_data_from_source(client, v_id)
            if not series_name:
                await message.reply_text("❌ لم يتم العثور على الحلقة")
                return
        else:
            series_name, ep_num, quality = data[0]
        
        keyboard = []
        if SHOW_MORE_BUTTONS and series_name:
            all_series_eps = db_query("SELECT ep_num, v_id FROM videos WHERE series_name = %s ORDER BY ep_num ASC LIMIT 50", (series_name,))
            if all_series_eps and len(all_series_eps) > 1:
                me = await client.get_me()
                bot_username = me.username
                row = []
                for o_ep, o_vid in all_series_eps:
                    if o_ep == ep_num and o_vid == v_id:
                        row.append(InlineKeyboardButton(f"✅ {o_ep}", url=f"https://t.me/{bot_username}?start={o_vid}"))
                    else:
                        row.append(InlineKeyboardButton(str(o_ep), url=f"https://t.me/{bot_username}?start={o_vid}"))
                    if len(row) == 5:
                        keyboard.append(row)
                        row = []
                if row: keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        try:
            await client.copy_message(
                message.chat.id, SOURCE_CHANNEL, int(v_id),
                caption=f"🎬 {series_name} - الحلقة {ep_num}\n📺 الجودة: {quality}",
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )
            db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
        except FloodWait as e:
            await message.reply_text(f"⏳ البوت مشغول، انتظر {e.value} ثانية")
            await asyncio.sleep(e.value)
            await start_cmd(client, message)
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
    else:
        welcome_text = """👋 **بوت المشاهدة الذكي**

📺 **طريقة الرفع:**
1️⃣ ارفع الفيديو
2️⃣ ارفع البوستر مع اسم المسلسل
3️⃣ اختر الجودة
4️⃣ أرسل رقم الحلقة

✅ **نشر تلقائي في قناة النشر**

🆘 @Mohsen_7e"""
        await message.reply_text(welcome_text)

# ===== [15] أوامر الإدارة (موجودة) =====
# ... (أوامر delete, delete_series, list, search, refresh_series, check_ep, stats, check_pending, reset_pending, test_publish, test, clear_limits, check_channel, update_series, reindex)

# ===== [16] إعداد قائمة المسلسلات =====
try:
    from series_menu import setup_series_menu
    setup_series_menu(app, db_query)
    print("✅ تم تحميل نظام قائمة المسلسلات")
except Exception as e:
    print(f"⚠️ لم يتم تحميل قائمة المسلسلات: {e}")

# ===== [17] إعداد نظام فحص المسلسلات =====
try:
    from series_scanner import setup_series_scanner
    setup_series_scanner(app, db_query)
    print("✅ تم تحميل نظام فحص المسلسلات")
except Exception as e:
    print(f"⚠️ لم يتم تحميل نظام فحص المسلسلات: {e}")

# ===== [18] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل البوت الذكي مع الاشتراك الإجباري...")
    init_database()
    
    while True:
        try:
            app.run()
        except FloodWait as e:
            wait_time = e.value
            print(f"⏳ FloodWait: انتظر {wait_time} ثانية")
            time.sleep(wait_time)
        except Exception as e:
            print(f"❌ خطأ: {e}")
            print("🔄 إعادة التشغيل بعد 5 ثواني...")
            time.sleep(5)

if __name__ == "__main__":
    main()
