import os
import psycopg2
import psycopg2.pool
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== 1. الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# تأكد في Railway أن الرابط يبدأ بـ postgres:// وليس postgresql://
DATABASE_URL = os.environ.get("DATABASE_URL").replace("postgresql://", "postgres://")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== 2. قاعدة البيانات المحمية من التعليق =====
db_pool = None

def get_pool():
    global db_pool
    if db_pool is None:
        try:
            # ضبط الاتصال لينقطع بعد 5 ثوانٍ إذا لم يستجب السيرفر (منعاً للدائرة الحمراء)
            db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require", connect_timeout=5)
        except Exception as e:
            logging.error(f"❌ Pool Creation Failed: {e}")
    return db_pool

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        pool = get_pool()
        if not pool: return None
        conn = pool.getconn()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchall() if fetch else None
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ DB Query Error: {e}")
        return None
    finally:
        if conn: get_pool().putconn(conn)

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, 
            poster_id TEXT, file_id TEXT, quality TEXT, 
            duration TEXT, status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0
        )""", fetch=False)
    try: db_query("ALTER TABLE videos ADD COLUMN IF NOT EXISTS file_id TEXT", fetch=False)
    except: pass

# ===== 3. محرك الإرسال (بدون تأخير) =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur, f_id=None):
    # فحص الاشتراك بسرعة
    is_subscribed = True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in ["left", "kicked"]: is_subscribed = False
    except: pass

    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    btns = []
    if res:
        row = []
        bot_info = await app.get_me()
        for vid, ename in res:
            label = f"✅️ {ename}" if str(vid) == str(v_id) else f"{ename}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={vid}"))
            if len(row) == 5: btns.append(row); row = []
        if row: btns.append(row)

    safe_title = " . ".join(list(escape(title)))
    cap = f"<b>📺 المسلسل : {safe_title}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n<b>💿 الجودة : {q}</b>\n<b>⏳ المدة : {dur}</b>"

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]] + btns) if not is_subscribed else (InlineKeyboardMarkup(btns) if btns else None)

    try:
        if f_id:
            await client.send_video(chat_id, video=f_id, caption=cap, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=markup)
    except Exception as e:
        await client.send_message(chat_id, f"🎬 {title} - حلقة {ep}\n⚠️ تعذر الإرسال: {e}")

# ===== 4. الأوامر واستقبال الميديا =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً {escape(message.from_user.first_name)}! ابحث عن المسلسلات في القناة.")
    
    v_id = message.command[1]
    # محاولة جلب البيانات مع وضع "خطة بديلة" لو فشلت القاعدة
    res = db_query("SELECT title, ep_num, quality, duration, file_id FROM videos WHERE v_id=%s", (v_id,))
    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        await message.reply_text("⏳ جاري جلب البيانات من السيرفر، يرجى المحاولة بعد لحظات...")

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    dur = f"{media.duration//60:02}:{media.duration%60:02}" if hasattr(media, 'duration') else "00:00"
    db_query("INSERT INTO videos (v_id, status, duration, file_id) VALUES (%s, 'waiting', %s, %s) ON CONFLICT (v_id) DO UPDATE SET file_id=%s", (v_id, dur, media.file_id, media.file_id), fetch=False)
    await message.reply_text("✅ تم. أرسل البوستر.")

# (بقية الدوال: receive_poster, set_quality, receive_ep_num تبقى كما هي في كودك السابق)
# ... [تم اختصارها هنا لسرعة الرد، احتفظ بها من الكود السابق]

if __name__ == "__main__":
    init_db()
    app.run()
