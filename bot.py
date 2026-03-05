import os
import psycopg2
import psycopg2.pool
import logging
import re
import asyncio
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

# ===== قاعدة البيانات (Pool) =====
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
        logging.error(f"❌ Database Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

# ===== وظائف التنظيف والاستخراج =====
def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(الحلقة|حلقة)?\s*\d+|\[.*?\]|الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep_num(text):
    if not text: return 0
    match = re.search(r'(?:الحلقة|حلقة|#)?\s*(\d+)', text)
    return int(match.group(1)) if match else 0

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return []
    btns, row, seen = [], [], set()
    me = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen: continue
        seen.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={v_id}"))
        if len(row) == 5: btns.append(row); row = []
    if row: btns.append(row)
    return btns

# ===== محرك الأرشفة التلقائية (On-Click) المصحح =====
async def auto_archive_logic(client, v_id_key):
    try:
        v_id_int = int(v_id_key)
        # جلب الفيديو للتأكد من وجوده
        msg = await client.get_messages(SOURCE_CHANNEL, v_id_int)
        if not msg or msg.empty: return None

        title, ep = "مسلسل مستعاد", 0
        
        # البحث في الرسائل الـ 10 التي تلي الفيديو (الأحدث منه)
        # نطلب الرسائل التي تبدأ من بعد الفيديو بـ 10 رسائل ونعود إليه
        async for m in client.get_chat_history(SOURCE_CHANNEL, limit=10, offset_id=v_id_int + 10):
            if m.id <= v_id_int: continue # لا نريد الفيديو نفسه بل ما بعده
                
            if m.photo and m.caption:
                title = clean_series_title(m.caption)
                if ep == 0: ep = extract_ep_num(m.caption)
            elif m.text and m.text.isdigit():
                ep = int(m.text)
                # إذا وصلنا للرقم الصريح، فغالباً انتهت بيانات الحلقة
                break

        # حفظ البيانات فوراً
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status) 
            VALUES (%s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, status='posted'
        """, (v_id_key, title, ep, title, ep), fetch=False)
        
        return (title, ep)
    except Exception as e:
        logging.error(f"Archive Logic Error: {e}")
        return None

# ===== Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا محمد في بوت الحلقات.")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
    
    if not res:
        # أرشفة تلقائية فورية عند أول ضغطة
        archive_res = await auto_archive_logic(client, v_id)
        if not archive_res:
            return await message.reply_text("❌ عذراً، لم يتم العثور على بيانات الحلقة في السورس.")
        title, ep = archive_res
    else:
        title, ep = res[0]

    # فحص الاشتراك
    if message.from_user.id != ADMIN_ID:
        try:
            m = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
            if m.status in ["left", "kicked"]:
                return await message.reply_text("⚠️ اشترك لمشاهدة الحلقة 👇", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        except: pass

    btns = await get_episodes_markup(title, v_id)
    # تجميل الاسم (توزيع الحروف)
    safe_title = " . ".join(list(title))
    cap = f"📺 <b>{safe_title}</b>\n🎞️ <b>الحلقة: {ep}</b>"
    
    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))
        db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    except:
        await message.reply_text("❌ الفيديو غير موجود حالياً في قناة السورس.")

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, status TEXT, views INTEGER DEFAULT 0)", fetch=False)
    logging.info("🚀 البوت يعمل الآن بنظام الأرشفة الذكية المصححة...")
    app.run()
