import os
import psycopg2
import logging
import re
from html import escape
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات (Logs)
logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية (تُسحب من إعدادات Railway) =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# تصحيح رابط قاعدة البيانات ليتوافق مع psycopg2
DATABASE_URL = os.environ.get("DATABASE_URL").replace("postgresql://", "postgres://")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003554018307
FORCE_SUB_LINK = "https://t.me/+PyUeOtPN1fs0NDA0"
PUBLIC_POST_CHANNEL = "@ramadan2206"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== نظام إدارة قاعدة البيانات (Connection Pool) =====
db_pool = pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")

def db_query(query, params=(), fetch=True):
    conn = db_pool.getconn()
    try:
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
        conn.rollback()
        return None
    finally:
        db_pool.putconn(conn)

def init_db():
    # إنشاء جدول الفيديوهات
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            quality TEXT,
            ep_num INTEGER,
            duration TEXT,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    # إنشاء جدول طلبات المسلسلات
    db_query("""
        CREATE TABLE IF NOT EXISTS series_requests (
            series_name TEXT PRIMARY KEY,
            request_count INTEGER DEFAULT 1,
            last_requester TEXT
        )
    """, fetch=False)
    logging.info("✅ Database Initialized Successfully.")

# ===== الدوال المساعدة =====
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    if res:
        for v_id, ep_num in res:
            if ep_num in seen_eps: continue
            seen_eps.add(ep_num)
            label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}"))
            if len(row) == 5:
                buttons.append(row); row = []
        if row: buttons.append(row)
    
    # أزرار البحث والطلب المضافة أسفل كل فيديو
    buttons.append([
        InlineKeyboardButton("🔍 البحث عن مسلسل", switch_inline_query_current_chat=""),
        InlineKeyboardButton("➕ طلب مسلسل", url="https://t.me/ramadan2206") # استبدل بيوزرك
    ])
    return buttons

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# ===== إرسال الفيديو النهائي =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    btns = await get_episodes_markup(title, v_id)
    is_subscribed = await check_subscription(client, user_id)
    
    safe_title = obfuscate_visual(escape(title))
    cap = (
        f"<b><a href='https://s6.gifyu.com/images/S6atp.gif'>&#8205;</a>📺 المسلسل : {safe_title}</b>\n"
        f"<b>🎞️ رقم الحلقة : {escape(str(ep))}</b>\n"
        f"<b>💿 الجودة : {escape(str(q or 'Original'))}</b>\n"
        f"<b>⏳ المدة : {escape(str(dur))}</b>\n\n🍿 مشاهدة ممتعة!"
    )

    if not is_subscribed:
        cap += "\n\n⚠️ <b>يجب الانضمام للقناة لمتابعة الحلقات 👇</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام (مهم)", url=FORCE_SUB_LINK)]] + btns)
    else:
        markup = InlineKeyboardMarkup(btns)

    try:
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, parse_mode=ParseMode.HTML, reply_markup=markup)
    except:
        await client.send_message(chat_id, f"🎬 {safe_title} - حلقة {ep}")

# ===== الأوامر والمعالجة =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>! 👋", parse_mode=ParseMode.HTML)
        return

    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    
    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        # جلب تلقائي وأرشفة من المصدر إذا كانت الحلقة غير مسجلة
        try:
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if source_msg and (source_msg.video or source_msg.document):
                cap = source_msg.caption or ""
                title = clean_series_title(cap)
                ep_num = int(re.findall(r'\d+', cap)[0]) if re.findall(r'\d+', cap) else 1
                db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT DO NOTHING", (v_id, title, ep_num), fetch=False)
                await send_video_final(client, message.chat.id, message.from_user.id, v_id, title, ep_num, "Original", "00:00:00")
        except:
            await message.reply_text("❌ الحلقة غير موجودة.")

@app.on_message(filters.command("requests") & filters.user(ADMIN_ID))
async def get_requests(client, message):
    top = db_query("SELECT series_name, request_count FROM series_requests ORDER BY request_count DESC LIMIT 10")
    text = "🔥 <b>أكثر المسلسلات المطلوبة:</b>\n\n"
    if top:
        for i, r in enumerate(top, 1): text += f"{i}. 🎬 <b>{r[0]}</b> ({r[1]} طلب)\n"
    else: text += "لا يوجد طلبات."
    await message.reply_text(text)

# ===== البحث الذكي ونظام "هل تقصد" =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "requests", "stats"]))
async def smart_search(client, message):
    user_text = message.text.strip()
    # تحويل الأرقام واستخراجها
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    norm_text = user_text.translate(trans)
    ep_num = int(re.findall(r'\d+', norm_text)[0]) if re.findall(r'\d+', norm_text) else None
    query = re.sub(r'\d+', '', norm_text).strip()

    if not query: return

    # البحث عن المسلسل
    res = db_query("SELECT v_id, title, ep_num, quality, duration FROM videos WHERE title ILIKE %s AND status='posted' ORDER BY (ep_num = %s) DESC LIMIT 1", (f"%{query}%", ep_num or 1))

    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, *res[0])
    else:
        # نظام الاقتراح
        first_word = query.split()[0]
        suggestion = db_query("SELECT DISTINCT title FROM videos WHERE title ILIKE %s LIMIT 1", (f"%{first_word}%",))
        if suggestion:
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ نعم", callback_data=f"c_{suggestion[0][0][:15]}_{ep_num or 0}"),
                InlineKeyboardButton("❌ لا", callback_data=f"r_{query[:20]}")
            ]])
            await message.reply_text(f"🔍 هل تقصد: <b>{suggestion[0][0]}</b>؟", reply_markup=markup)
        else:
            await record_request(client, message, query)

async def record_request(client, message, name):
    db_query("INSERT INTO series_requests (series_name, request_count) VALUES (%s, 1) ON CONFLICT (series_name) DO UPDATE SET request_count = series_requests.request_count + 1", (name,), fetch=False)
    res = db_query("SELECT request_count FROM series_requests WHERE series_name = %s", (name,))
    count = res[0][0] if res else 1
    if count >= 20: await client.send_message(ADMIN_ID, f"🔥 <b>طلب قوي ({count}):</b> {name}")
    await message.reply_text("✅ تم إرسال طلبك للإدارة.")

@app.on_callback_query(filters.regex("^(c_|r_)"))
async def cb_handler(client, cb):
    data = cb.data.split("_")
    if data[0] == "c":
        res = db_query("SELECT v_id, title, ep_num, quality, duration FROM videos WHERE title ILIKE %s ORDER BY (ep_num = %s) DESC LIMIT 1", (f"%{data[1]}%", int(data[2])))
        if res: 
            await cb.message.delete()
            await send_video_final(client, cb.message.chat.id, cb.from_user.id, *res[0])
    else:
        await cb.message.edit_text("✅ تم تسجيل طلبك.")

# ===== استقبال الحلقات الجديدة (الأدمن) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO UPDATE SET status='waiting'", (v_id,), fetch=False)
    await message.reply_text("✅ تم استلام الفيديو. أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title = res[0][0], clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='posted', ep_num=1 WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"🚀 تم نشر المسلسل: {title}")

if __name__ == "__main__":
    init_db()
    app.run()
