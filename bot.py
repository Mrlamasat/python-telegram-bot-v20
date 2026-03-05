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
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== 2. قاعدة البيانات (نظام المجمع والـ File ID) =====
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
        if fetch: result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER,
            poster_id TEXT,
            file_id TEXT,
            quality TEXT,
            duration TEXT,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    # تحديث الجدول القديم ليدعم الـ File ID
    try: db_query("ALTER TABLE videos ADD COLUMN IF NOT EXISTS file_id TEXT", fetch=False)
    except: pass

# ===== 3. الدوال المساعدة =====
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅️ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    return buttons

# ===== 4. محرك الإرسال الذكي (الحل النهائي للدائرة) =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur, f_id=None):
    # إذا لم يكن لدينا file_id، سنحاول جلبه من المصدر وتخزينه فوراً
    if not f_id:
        try:
            msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if msg and (msg.video or msg.animation):
                f_id = (msg.video or msg.animation).file_id
                db_query("UPDATE videos SET file_id=%s WHERE v_id=%s", (f_id, v_id), fetch=False)
        except Exception as e:
            logging.error(f"⚠️ Failed to cache file_id for {v_id}: {e}")

    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    
    # فحص الاشتراك (بسرعة وبدون تعليق)
    is_subscribed = True
    if user_id != ADMIN_ID:
        try:
            member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
            if member.status in ["left", "kicked"]: is_subscribed = False
        except: pass

    btns = await get_episodes_markup(title, v_id)
    safe_title = obfuscate_visual(escape(title))
    cap = (f"<b>📺 المسلسل : {safe_title}</b>\n"
           f"<b>🎞️ رقم الحلقة : {escape(str(ep))}</b>\n"
           f"<b>💿 الجودة : {escape(str(q))}</b>\n"
           f"<b>⏳ المدة : {escape(str(dur))}</b>\n\n🍿 <b>مشاهدة ممتعة!</b>")

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]] + (btns if btns else [])) if not is_subscribed else (InlineKeyboardMarkup(btns) if btns else None)

    try:
        # الإرسال عبر file_id هو الأسرع على الإطلاق
        if f_id:
            await client.send_video(chat_id, video=f_id, caption=cap, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            # النسخ التقليدي كخيار أخير
            await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=markup)
    except Exception as e:
        logging.error(f"❌ Final Send Failed: {e}")
        await client.send_message(chat_id, f"🎬 {safe_title} - حلقة {ep}\n(الملف قيد التحديث، جرب لاحقاً)")

# ===== 5. استقبال الميديا الجديدة (مع تخزين الـ file_id فوراً) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    f_id = media.file_id
    d = media.duration if hasattr(media, 'duration') else 0
    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    db_query("INSERT INTO videos (v_id, status, duration, file_id) VALUES (%s, 'waiting', %s, %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', file_id=%s", (v_id, dur, f_id, f_id), fetch=False)
    await message.reply_text(f"✅ تم استلام الميديا. أرسل البوستر.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id, title = res[0][0], clean_series_title(message.caption or "")
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: {escape(title)}\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_", 2)
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats", "del", "clear"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    b_info = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    caption = f"🎬 <b>{safe_t}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n<b>الجودة: [{q}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")]])
    await client.send_photo(PUBLIC_POST_CHANNEL, p_id, caption=caption, reply_markup=markup)
    await message.reply_text("🚀 نُشر بنجاح.")

# ===== 6. أوامر المستخدم =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً {escape(message.from_user.first_name)}!")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration, file_id FROM videos WHERE v_id=%s", (v_id,))
    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        await message.reply_text("❌ غير موجود.")

if __name__ == "__main__":
    init_db()
    app.run()
