import os
import psycopg2
import psycopg2.pool
import logging
import re
import difflib
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from pyrogram.enums import ParseMode

# إعداد السجلات (Logs)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الأساسية (تأكد من وجودها في Railway Variables) =====
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

# ===== إدارة قاعدة البيانات (Pool) =====
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
        conn.set_client_encoding('UTF8')
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

# ===== دوال التنظيف والاستخراج الذكي =====
def convert_ar_no(text):
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return text.translate(trans)

def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'[أإآأ]', 'ا', text); text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ى', 'ي', text); text = re.sub(r'^(ال)', '', text)
    return re.sub(r'\s+', '', text)

def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text) 
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

# ===== نظام أزرار الحلقات =====
async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    me = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={v_id}"))
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    return buttons

# ===== نظام النشر التلقائي الذكي =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def auto_post_handler(client, message):
    v_id = str(message.id)
    caption = message.caption or ""
    title = clean_series_title(caption)
    ep_match = re.search(r'(\d+)', caption)
    real_ep = int(ep_match.group(1)) if ep_match else 1
    
    db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s", (v_id, title, real_ep, title, real_ep), fetch=False)
    
    me = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    pub_text = f"🎬 <b>{safe_t}</b>\n\n📌 <b>الحلقة رقم: [ {real_ep} ]</b>\n\n👇 اضغط هنا للمشاهدة فوراً"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ شاهد الحلقة الآن", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    try:
        await client.send_message(PUBLIC_POST_CHANNEL, pub_text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"❌ Auto-post failed: {e}")

# ===== معالجة الـ Start وجلب الفيديوهات (الإصلاح الجذري للاشتراك) =====
@app.on_message(filters.command("start") & filters.private)
async def handle_start(client, message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(f"مرحباً بك يا <b>{escape(message.from_user.first_name)}</b>! ابحث عن مسلسلك بكتابة اسمه..", parse_mode=ParseMode.HTML)
    
    v_id = message.command[1]
    
    # 1. فحص الاشتراك الإجباري (استثناء الأدمن ومعالجة الأخطاء)
    if user_id != ADMIN_ID:
        try:
            user_status = await client.get_chat_member(int(FORCE_SUB_CHANNEL), user_id)
            if user_status.status in ["left", "kicked"]:
                return await message.reply_text(
                    "⚠️ **يجب الانضمام لقناتنا لمشاهدة الحلقة:**",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 اضغط هنا للانضمام", url=FORCE_SUB_LINK)]])
                )
        except Exception:
            # إذا فشل الفحص تقنياً، نمرر المستخدم لضمان تجربة سلسة
            pass

    # 2. جلب الحلقة من المصدر وتحديث البيانات
    try:
        source_chat = await client.get_chat(int(SOURCE_CHANNEL))
        msg = await client.get_messages(source_chat.id, int(v_id))
        
        if msg and msg.caption:
            title = clean_series_title(msg.caption)
            ep_match = re.search(r'(\d+)', msg.caption)
            ep = int(ep_match.group(1)) if ep_match else 1
            db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s", (v_id, title, ep, title, ep), fetch=False)
        else:
            res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
            title, ep = res[0] if res else ("مسلسل", 1)

        btns = await get_episodes_markup(title, v_id)
        cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ حلقة : {ep}</b>"
        
        await client.copy_message(message.chat.id, source_chat.id, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))
    except Exception as e:
        logging.error(f"Error in start: {e}")
        await message.reply_text("❌ لم نتمكن من جلب هذه الحلقة حالياً.")

# ===== محرك البحث الذكي =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats", "del"]))
async def advanced_search(client, message):
    raw_input = convert_ar_no(message.text)
    query_norm = normalize_text(re.sub(r'\d+', '', raw_input))
    all_titles_res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    if not all_titles_res: return
    
    all_titles = [r[0] for r in all_titles_res]
    matches = [t for t in all_titles if query_norm in normalize_text(t)]

    if matches:
        title = matches[0]
        btns = await get_episodes_markup(title, 0)
        await message.reply_text(f"🔍 عثرنا على مسلسل **{title}**\nاختر الحلقة التي تريدها:", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await message.reply_text("❌ لم يتم العثور على المسلسل.")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, status TEXT DEFAULT 'posted', views INTEGER DEFAULT 0)")
    conn.commit(); cur.close(); conn.close()
    logging.info("🚀 Bot is running successfully...")
    app.run()
