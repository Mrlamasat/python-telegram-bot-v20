import os
import psycopg2
import psycopg2.pool
import logging
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
db_pool = None
def get_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")
    return db_pool

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        pool = get_pool()
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return res
    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

# ===== تنظيف البيانات =====
def clean_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(الحلقة|حلقة)?\s*\d+|\[.*?\]|الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep(text):
    match = re.search(r'(?:الحلقة|حلقة|#)?\s*(\d+)', text or "")
    return int(match.group(1)) if match else 0

# ===== نظام البوستر والأرشفة =====
async def get_poster_id(client, v_id):
    """البحث عن معرف الصورة (البوستر) الفريد"""
    for i in range(1, 6):
        m = await client.get_messages(SOURCE_CHANNEL, v_id - i)
        if m and m.photo: return m.photo.file_unique_id
    return None

async def scan_channel_by_poster(client, poster_id, start_id):
    """مسح القناة لربط الحلقات التي لها نفس البوستر"""
    search_ids = [i for i in range(start_id - 150, start_id + 150)]
    messages = await client.get_messages(SOURCE_CHANNEL, search_ids)
    last_poster = None
    for m in messages:
        if not m: continue
        if m.photo: last_poster = m.photo.file_unique_id
        elif (m.video or m.document) and last_poster == poster_id:
            ep = extract_ep(m.caption)
            title = clean_title(m.caption)
            db_query("INSERT INTO videos (v_id, title, ep_num, poster_id, status) VALUES (%s, %s, %s, %s, 'posted') ON CONFLICT DO NOTHING", 
                     (str(m.id), title, ep, poster_id), fetch=False)

# ===== توليد الأزرار =====
async def get_markup(poster_id, current_v_id, page=0):
    # جلب الحلقات بناءً على البوستر المشترك
    res = db_query("SELECT v_id, ep_num FROM videos WHERE poster_id = %s ORDER BY ep_num ASC", (poster_id,))
    if not res or len(res) <= 1: return None
    
    btns, seen = [], set()
    for v_id, ep_num in res:
        if ep_num in seen: continue
        seen.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        btns.append(InlineKeyboardButton(label, callback_data=f"ep_{v_id}"))
    
    # تقسيم الصفوف (5 أزرار لكل صف)
    rows = [btns[i:i + 5] for i in range(0, len(btns), 5)]
    return InlineKeyboardMarkup(rows)

# ===== المعالجات =====
@app.on_callback_query(filters.regex(r"^ep_"))
async def handle_ep(client, query):
    v_id = query.data.split("_")[1]
    res = db_query("SELECT title, ep_num, poster_id FROM videos WHERE v_id=%s", (v_id,))
    if not res: return await query.answer("خطأ!")
    
    title, ep, p_id = res[0]
    markup = await get_markup(p_id, v_id)
    safe_title = " . ".join(list(title[:30]))
    
    await query.message.delete()
    await client.copy_message(query.message.chat.id, SOURCE_CHANNEL, int(v_id), 
                              caption=f"📺 <b>{safe_title}</b>\n🎞️ <b>الحلقة: {ep}</b>", 
                              reply_markup=markup)

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2: return await message.reply("أهلاً بك يا محمد.")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, poster_id FROM videos WHERE v_id=%s", (v_id,))
    
    if not res:
        p_id = await get_poster_id(client, int(v_id))
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        title = clean_title(msg.caption)
        ep = extract_ep(msg.caption)
        db_query("INSERT INTO videos (v_id, title, ep_num, poster_id, status) VALUES (%s, %s, %s, %s, 'posted')", 
                 (v_id, title, ep, p_id), fetch=False)
        if p_id: asyncio.create_task(scan_channel_by_poster(client, p_id, int(v_id)))
    else:
        title, ep, p_id = res[0]

    # فحص الاشتراك
    try:
        m = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        if m.status in ["left", "kicked"]:
            return await message.reply("⚠️ اشترك أولاً", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
    except: pass

    markup = await get_markup(p_id, v_id)
    safe_title = " . ".join(list(title[:30]))
    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), 
                              caption=f"📺 <b>{safe_title}</b>\n🎞️ <b>الحلقة: {ep}</b>", 
                              reply_markup=markup)

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, poster_id TEXT, status TEXT)", fetch=False)
    app.run()
