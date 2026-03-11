import os, psycopg2, logging, re, asyncio, time, random
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# استيراد الوظائف من الملف الثاني
from series_menu import setup_series_menu, refresh_series_menu

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات المحدثة =====
API_ID = int(os.environ.get("API_ID", "24119842")) 
API_HASH = os.environ.get("API_HASH", "82428587635c05c6d3dfd6835be26002")
BOT_TOKEN = "81619590433:AAFhbBbIdA4tGYpmn9gCwKv6TvZs4BbkSzM" # توكن البوت الجديد
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
PUBLISH_CHANNEL = -1003689965691  # قناة النشر الجديدة

SHOW_MORE_BUTTONS = True
user_last_request = {}
REQUEST_LIMIT = 5
TIME_WINDOW = 10

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] الدوال المساعدة =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد"]

def encrypt_title(title):
    if not title: return "محتوى"
    words = title.split()
    if words:
        word = random.choice(words)
        return f"🎬 {word[::-1]} {random.randint(10,99)}"
    return f"🎬 {random.choice(ENCRYPTION_WORDS)} {random.randint(10,99)}"

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
            logging.error(f"DB Error: {e}")
            if attempt == retry - 1: return [] if fetch else None
            time.sleep(1)

def init_database():
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, series_name TEXT, ep_num INTEGER DEFAULT 0, quality TEXT DEFAULT 'HD', views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS posters (poster_id BIGINT PRIMARY KEY, series_name TEXT, video_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT, first_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS pending_posts (video_id TEXT PRIMARY KEY, step TEXT, poster_id BIGINT, quality TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS views_log (id SERIAL PRIMARY KEY, v_id TEXT, viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    print("✅ قاعدة البيانات جاهزة")

def extract_series_name(text):
    if not text: return None
    patterns = [r'^(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$', r'^(.+?)\s+(\d+)$', r'^مسلسل\s+(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$']
    for p in patterns:
        match = re.search(p, text.strip())
        if match: return match.group(1).strip()
    return text.strip()

def extract_episode_number(text):
    if not text: return 0
    match = re.search(r'(?:حلقة|حلقه|الحلقة|الحلقه)\s*[:\-]?\s*(\d+)', text)
    if match: return int(match.group(1))
    nums = re.findall(r'\d+', text)
    return int(nums[-1]) if nums else 0

async def get_video_data_from_source(client, v_id):
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not msg or not msg.video: return None, None, None
        s_name = extract_series_name(msg.caption)
        ep = extract_episode_number(msg.caption)
        db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, 'HD') ON CONFLICT (v_id) DO UPDATE SET series_name=EXCLUDED.series_name, ep_num=EXCLUDED.ep_num", (v_id, s_name, ep), fetch=False)
        return s_name, ep, "HD"
    except: return None, None, None

# ===== [3] معالجة الرسائل والقناة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.photo))
async def monitor_source(client, message):
    if message.video:
        v_id = str(message.id)
        s_name = extract_series_name(message.caption)
        ep = extract_episode_number(message.caption)
        if s_name and ep > 0:
            db_query("INSERT INTO videos (v_id, series_name, ep_num) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET series_name=EXCLUDED.series_name, ep_num=EXCLUDED.ep_num", (v_id, s_name, ep), fetch=False)
            await refresh_series_menu(client, db_query)
            # النشر التلقائي
            me = await client.get_me()
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
            await client.copy_message(PUBLISH_CHANNEL, SOURCE_CHANNEL, int(v_id), caption=f"🎬 **{encrypt_title(s_name)}**\n🔢 **الحلقة {ep}**", reply_markup=btn)
        else:
            db_query("INSERT INTO pending_posts (video_id, step) VALUES (%s, 'waiting_for_poster')", (v_id,), fetch=False)
            await message.reply_text("📹 فيديو جديد.. أرسل البوستر الآن.")

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    if len(message.command) > 1:
        v_id = message.command[1]
        data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        if data:
            s_name, ep, q = data[0]
            # نظام الأزرار المجمعة
            all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE series_name = %s ORDER BY ep_num ASC", (s_name,))
            kb = []
            row = []
            for e_num, e_vid in all_eps:
                txt = f"✅ {e_num}" if e_vid == v_id else str(e_num)
                row.append(InlineKeyboardButton(txt, url=f"https://t.me/{(await client.get_me()).username}?start={e_vid}"))
                if len(row) == 5: kb.append(row); row = []
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"🎬 {s_name} - حلقة {ep}\n📺 الجودة: {q}", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await message.reply_text("👋 أهلاً بك في بوت المشاهدة المطور!")

if __name__ == "__main__":
    init_database()
    setup_series_menu(app, db_query)
    print("🚀 Bot Rama Started!")
    app.run()
