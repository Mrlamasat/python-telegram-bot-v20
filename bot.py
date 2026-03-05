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

# ===== الإعدادات الأساسية =====
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
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 15, DATABASE_URL, sslmode="require")
    return db_pool

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        pool = get_pool()
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

# ===== وظائف المعالجة الذكية =====
def obfuscate_visual(text):
    return " . ".join(list(text)) if text else ""

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

# ===== نظام الأرشفة التلقائية عند الضغط على الرابط (On-Demand) =====
async def auto_archive_on_click(client, v_id_key):
    try:
        # 1. جلب رسالة الفيديو من السورس
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id_key))
        if not msg or not (msg.video or msg.document or msg.animation):
            return None

        # 2. البحث عن "البوستر" والترقيم في الرسائل الـ 5 التالية (ترتيب زمني صاعد)
        title, ep = "مسلسل غير معروف", 0
        async for m in client.get_chat_history(SOURCE_CHANNEL, limit=5, offset_id=int(v_id_key), reverse=True):
            if m.photo and m.caption:
                title = clean_series_title(m.caption)
                ep = extract_ep_num(m.caption)
            elif m.text and m.text.isdigit():
                ep = int(m.text) # ترقيمك اليدوي الذي تضعه بعد الصورة

        # 3. حفظ البيانات في القاعدة
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status, views) 
            VALUES (%s, %s, %s, 'posted', 1)
            ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, status='posted'
        """, (v_id_key, title, ep, title, ep), fetch=False)
        
        return (title, ep)
    except Exception as e:
        logging.error(f"❌ Auto-Archive Failed: {e}")
        return None

# ===== معالجة أوامر المستخدم (Start) =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>!")
    
    v_id_key = message.command[1]
    
    # محاولة البحث في القاعدة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id_key,))
    
    if not res:
        # إذا لم توجد، نقوم بالأرشفة الفورية من السورس
        wait_msg = await message.reply_text("⏳ جاري استعادة بيانات الحلقة من الأرشيف...")
        archive_res = await auto_archive_on_click(client, v_id_key)
        await wait_msg.delete()
        if archive_res:
            title, ep = archive_res
        else:
            return await message.reply_text("❌ عذراً، لم نتمكن من العثور على ملف الحلقة في السورس.")
    else:
        title, ep = res[0]

    # فحص الاشتراك
    if message.from_user.id != ADMIN_ID:
        try:
            m = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
            if m.status in ["left", "kicked"]:
                return await message.reply_text("⚠️ اشترك لمشاهدة الحلقة 👇", 
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        except: pass

    # تحديث المشاهدات وإرسال المرفق
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id_key,), fetch=False)
    btns = await get_episodes_markup(title, v_id_key)
    safe_t = obfuscate_visual(escape(title))
    cap = f"<b>📺 المسلسل : {safe_t}</b>\n<b>🎞️ الحلقة : {ep}</b>"
    
    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id_key), caption=cap, reply_markup=InlineKeyboardMarkup(btns))
    except:
        await message.reply_text("❌ خطأ: ملف الفيديو غير موجود في قناة المصدر.")

# ===== استقبال الرفع الجديد (اليدوي) لضمان الأرشفة الفورية =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def on_new_video(client, message):
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO NOTHING", (str(message.id),), fetch=False)

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def on_new_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if res:
        v_id = res[0][0]
        title = clean_series_title(message.caption or "")
        db_query("UPDATE videos SET title=%s, status='posted' WHERE v_id=%s", (title, v_id), fetch=False)
        await message.reply_text(f"✅ تم ربط البوستر بالفيديو {v_id}. سيتم تحديد رقم الحلقة تلقائياً عند الضغط أو يدوياً.")

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, poster_id TEXT, quality TEXT, duration TEXT, status TEXT, views INTEGER DEFAULT 0)", fetch=False)
    logging.info("🚀 البوت يعمل الآن بنظام الأرشفة الذكية عند الطلب...")
    app.run()
