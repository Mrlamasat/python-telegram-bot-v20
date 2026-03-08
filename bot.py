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
    if not title: return "محتوى"
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
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, series_name TEXT, ep_num INTEGER DEFAULT 0, quality TEXT DEFAULT 'HD', views INTEGER DEFAULT 0)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS posters (poster_id BIGINT PRIMARY KEY, series_name TEXT, video_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT, first_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS pending_posts (video_id TEXT PRIMARY KEY, step TEXT, poster_id BIGINT, quality TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
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

# ===== [9] مراقبة قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.photo))
async def monitor_source(client, message):
    try:
        if message.video:
            v_id = str(message.id)
            db_query("INSERT INTO pending_posts (video_id, step) VALUES (%s, 'waiting_for_poster') ON CONFLICT (video_id) DO UPDATE SET step = 'waiting_for_poster'", (v_id,), fetch=False)
            await message.reply_text(f"📹 تم استلام الفيديو ({v_id})\nارفع البوستر الآن.")
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
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("HD", callback_data=f"q_HD_{video_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{video_id}")]])
                await message.reply_text(f"🖼 تم ربط {s_name}\nاختر الجودة:", reply_markup=kb)
    except Exception as e: logging.error(f"Error: {e}")

# ===== [10] معالجة الجودة =====
@app.on_callback_query(filters.regex(r"^q_"))
async def handle_quality(client, cb):
    _, quality, v_id = cb.data.split('_')
    db_query("UPDATE pending_posts SET step = 'waiting_for_episode', quality = %s WHERE video_id = %s", (quality, v_id), fetch=False)
    await cb.message.edit_text(f"📊 الجودة: {quality}\nأرسل رقم الحلقة الآن.")

# ===== [11] استقبال رقم الحلقة (تم إصلاح الخطأ هنا) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.regex(r"^/"))
async def receive_episode(client, message):
    ep_num = extract_episode_number(message.text)
    if ep_num == 0: return

    pending = db_query("SELECT video_id, poster_id, quality FROM pending_posts WHERE step = 'waiting_for_episode' ORDER BY created_at DESC LIMIT 1")
    if not pending: return

    v_id, p_id, q = pending[0]
    poster_data = db_query("SELECT series_name FROM posters WHERE poster_id = %s", (p_id,))
    if not poster_data: return
    s_name = poster_data[0][0]

    db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, %s)", (v_id, s_name, ep_num, q), fetch=False)
    db_query("DELETE FROM pending_posts WHERE video_id = %s", (v_id,), fetch=False)

    try:
        encrypted = encrypt_title(s_name)
        me = await client.get_me()
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
        caption = f"🎬 **{encrypted}**\n🔢 **الحلقة {ep_num}**\n📺 **الجودة {q}**"
        await client.copy_message(PUBLISH_CHANNEL, SOURCE_CHANNEL, int(p_id), caption=caption, reply_markup=btn)
        await message.reply_text(f"✅ تم النشر: {s_name} - حلقة {ep_num}")
    except Exception as e: logging.error(f"Publish error: {e}")

# ===== [12] التشغيل =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        if data:
            s_name, ep, q = data[0]
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"🎬 {s_name} - حلقة {ep}\n📺 الجودة: {q}")
    else:
        await message.reply_text("👋 أهلاً بك محمد!")

if __name__ == "__main__":
    init_database()
    print("🚀 يعمل الآن...")
    app.run()
