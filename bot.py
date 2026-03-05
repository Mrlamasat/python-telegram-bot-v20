import os
import psycopg2
import psycopg2.pool
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
PUBLIC_POST_CHANNEL = -1003554018307
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات =====
db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode="require")

def db_query(query, params=(), fetch=True):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return res
    finally:
        db_pool.putconn(conn)

# ===== دوال المساعدة =====
def clean_title(text):
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text or "مسلسل").strip()

async def get_eps_markup(title, current_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    buttons, row = [], []
    me = await app.get_me()
    for v_id, ep in res:
        label = f"✅ {ep}" if str(v_id) == str(current_id) else f"{ep}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={v_id}"))
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    return buttons

# ===== نظام النشر التلقائي الذكي =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def auto_post(client, message):
    v_id = str(message.id)
    caption = message.caption or ""
    title = clean_title(caption)
    ep_match = re.search(r'(\d+)', caption)
    ep = int(ep_match.group(1)) if ep_match else 1
    
    # حفظ الحلقة في القاعدة فوراً
    db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s", (v_id, title, ep, title, ep), fetch=False)
    
    # توليد منشور النشر التلقائي
    me = await app.get_me()
    pub_cap = f"🎬 <b>{title} - الحلقة {ep}</b>\n\nاضغط على الزر أدناه لمشاهدة الحلقة مباشرة 👇"
    # الرابط هنا يستخدم v_id الحلقة الحالية لضمان فتحها هي تحديداً
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ شاهد الحلقة الآن", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    await client.send_message(PUBLIC_POST_CHANNEL, pub_cap, reply_markup=markup, parse_mode=ParseMode.HTML)

# ===== معالجة طلب الحلقة =====
@app.on_message(filters.command("start") & filters.private)
async def handle_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك! ابحث عن مسلسلك المفضل.")
    
    v_id = message.command[1]
    # محاولة جلب البيانات من القاعدة أو من المصدر مباشرة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
    
    try:
        source_chat = await client.get_chat(int(SOURCE_CHANNEL))
        msg = await client.get_messages(source_chat.id, int(v_id))
        
        title = clean_title(msg.caption) if msg.caption else (res[0][0] if res else "مسلسل")
        ep = int(re.search(r'\d+', msg.caption).group()) if msg.caption and re.search(r'\d+', msg.caption) else (res[0][1] if res else 1)
        
        btns = await get_eps_markup(title, v_id)
        cap = f"<b>📺 {title} - حلقة {ep}</b>"
        
        await client.copy_message(message.chat.id, source_chat.id, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.reply_text("❌ لم يتم العثور على هذه الحلقة في المصدر.")

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, status TEXT DEFAULT 'posted')", fetch=False)
    app.run()
