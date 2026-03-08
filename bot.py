import os, psycopg2, logging, re, asyncio, time, random
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
PUBLISH_CHANNEL = -1003554018307

# ===== [1.1] التحكم في المزيد من الحلقات =====
SHOW_MORE_BUTTONS = True

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] كلمات عشوائية للتشفير =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد"]

def encrypt_title(title):
    """تشفير اسم المسلسل للقناة فقط"""
    if not title:
        return "محتوى"
    words = title.split()
    if words:
        word = random.choice(words)
        return f"🎬 {word[::-1]} {random.randint(10,99)}"
    return f"🎬 {random.choice(ENCRYPTION_WORDS)} {random.randint(10,99)}"

# ===== [3] دالة قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
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
        logging.error(f"DB Error: {e}")
        return []

# ===== [4] إنشاء الجداول =====
def init_database():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            series_name TEXT,
            ep_num INTEGER DEFAULT 0,
            quality TEXT DEFAULT 'HD',
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS posters (
            poster_id BIGINT PRIMARY KEY,
            series_name TEXT,
            video_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS pending_posts (
            video_id TEXT PRIMARY KEY,
            step TEXT,
            poster_id BIGINT,
            quality TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دوال الاستخراج =====
def extract_series_name(text):
    if not text: return None
    patterns = [r'^(.+?)\s+(?:حلقة|حلقه)\s+\d+$', r'^(.+?)\s+(\d+)$', r'^(.+?)\s*-\s*(\d+)$']
    for pattern in patterns:
        match = re.search(pattern, text.strip())
        if match: return match.group(1).strip()
    return text.strip()[:50]

def extract_episode_number(text):
    if not text: return 0
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 0

def extract_series_from_video(text, v_id):
    series = extract_series_name(text)
    if not series:
        digits = re.sub(r'\D', '', v_id)
        suffix = digits[-3:] if len(digits) >= 3 else digits
        return f"مسلسل {suffix}"
    return series

# ===== [6] دالة أزرار الحلقات =====
def get_episode_buttons(series_name, current_id, bot_user):
    if not series_name: return []
    eps = db_query("SELECT ep_num, v_id FROM videos WHERE series_name = %s ORDER BY ep_num ASC LIMIT 50", (series_name,))
    if not eps or len(eps) < 2: return []
    keyboard, row = [], []
    for ep, vid in eps:
        label = f"• {ep} •" if str(vid) == str(current_id) else str(ep)
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_user}?start={vid}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return keyboard

# ===== [9] مراقبة قناة المصدر (فيديو وصور) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.photo))
async def monitor_source(client, message):
    try:
        if message.video:
            v_id = str(message.id)
            db_query("INSERT INTO pending_posts (video_id, step) VALUES (%s, 'waiting_for_poster') ON CONFLICT (video_id) DO UPDATE SET step = 'waiting_for_poster'", (v_id,), fetch=False)
            await message.reply_text(f"📹 **تم استلام الفيديو ({v_id})**\nالآن ارفع البوستر واكتب اسم المسلسل في الوصف.")
            
        elif message.photo:
            poster_id = message.id
            series_name = extract_series_name(message.caption or "")
            if not series_name:
                await message.reply_text("⚠️ يرجى كتابة اسم المسلسل في وصف البوستر!")
                return
            
            pending = db_query("SELECT video_id FROM pending_posts WHERE step = 'waiting_for_poster' ORDER BY created_at DESC LIMIT 1")
            if pending:
                video_id = pending[0][0]
                db_query("INSERT INTO posters (poster_id, series_name, video_id) VALUES (%s, %s, %s)", (poster_id, series_name, video_id), fetch=False)
                db_query("UPDATE pending_posts SET step = 'waiting_for_quality', poster_id = %s WHERE video_id = %s", (poster_id, video_id), fetch=False)
                
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("HD", callback_data=f"quality_HD_{video_id}"),
                    InlineKeyboardButton("SD", callback_data=f"quality_SD_{video_id}"),
                    InlineKeyboardButton("4K", callback_data=f"quality_4K_{video_id}")
                ]])
                await message.reply_text(f"🖼 **تم ربط البوستر بمسلسل: {series_name}**\nاختر الجودة الآن:", reply_markup=keyboard)

    except Exception as e:
        logging.error(f"Error in monitor: {e}")

# ===== [10] معالجة الجودة =====
@app.on_callback_query(filters.regex(r"^quality_"))
async def handle_quality(client, callback_query):
    _, quality, video_id = callback_query.data.split('_')
    db_query("UPDATE pending_posts SET step = 'waiting_for_episode', quality = %s WHERE video_id = %s", (quality, video_id), fetch=False)
    await callback_query.message.edit_text(f"📊 الجودة المختارة: **{quality}**\nأرسل الآن **رقم الحلقة فقط** (مثال: 20)")

# ===== [11] استقبال رقم الحلقة والنشر التلقائي (الإصلاح الجذري) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command)
async def receive_episode(client, message):
    ep_num = extract_episode_number(message.text)
    if ep_num == 0: return

    pending = db_query("SELECT video_id, poster_id, quality FROM pending_posts WHERE step = 'waiting_for_episode' ORDER BY created_at DESC LIMIT 1")
    if not pending: return

    video_id, poster_id, quality = pending[0]
    poster_data = db_query("SELECT series_name FROM posters WHERE poster_id = %s", (poster_id,))
    if not poster_data: return
    series_name = poster_data[0][0]

    # حفظ البيانات
    db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET series_name=EXCLUDED.series_name, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality", (video_id, series_name, ep_num, quality), fetch=False)
    db_query("DELETE FROM pending_posts WHERE video_id = %s", (video_id,), fetch=False)

    # النشر التلقائي
    try:
        encrypted = encrypt_title(series_name)
        me = await client.get_me()
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={video_id}")]])
        caption = f"🎬 **{encrypted}**\n🔢 **الحلقة {ep_num}**\n📺 **الجودة {quality}**"

        await client.copy_message(chat_id=PUBLISH_CHANNEL, from_chat_id=SOURCE_CHANNEL, message_id=poster_id, caption=caption, reply_markup=btn)
        await message.reply_text(f"✅ تم الحفظ والنشر بنجاح!\nالمسلسل: {series_name} | الحلقة: {ep_num}")
    except Exception as e:
        await message.reply_text(f"⚠️ تم الحفظ ولكن فشل النشر: {e}")

# ===== [12] الأوامر العامة =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id, username, first_name) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET last_used=CURRENT_TIMESTAMP", (message.from_user.id, message.from_user.username, message.from_user.first_name), fetch=False)
    
    if len(message.command) > 1:
        v_id = message.command[1]
        data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        if data:
            s_name, ep, q = data[0]
            kb = get_episode_buttons(s_name, v_id, (await client.get_me()).username)
            kb.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"<b>🎬 {s_name} - حلقة {ep}</b>\n📺 الجودة: {q}", reply_markup=InlineKeyboardMarkup(kb))
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        await message.reply_text("👋 أهلاً بك في بوت المشاهدة!\nارفع في قناة المصدر للمتابعة.")

@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    v_count = db_query("SELECT COUNT(*) FROM videos")[0][0]
    u_count = db_query("SELECT COUNT(*) FROM users")[0][0]
    await message.reply_text(f"📊 الإحصائيات:\n📁 الفيديوهات: {v_count}\n👥 المستخدمين: {u_count}")

@app.on_message(filters.command("reset_pending") & filters.user(ADMIN_ID))
async def reset_pending(client, message):
    db_query("DELETE FROM pending_posts", fetch=False)
    await message.reply_text("✅ تم تنظيف الطلبات المعلقة.")

if __name__ == "__main__":
    init_database()
    print("🚀 البوت يعمل الآن...")
    app.run()
