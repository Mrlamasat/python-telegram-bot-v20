import os
import psycopg2
import psycopg2.pool
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات لمراقبة الأخطاء في Railway
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== 1. الإعدادات الأساسية =====
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

# ===== 2. نظام مجمع الاتصالات (Connection Pool) =====
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

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER,
            poster_id TEXT,
            quality TEXT,
            duration TEXT,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    logging.info("✅ Database initialized.")

# ===== 3. الدوال المساعدة =====
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def get_episodes_markup(title, current_v_id):
    res = db_query(
        "SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC",
        (title,)
    )
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

async def check_subscription(client, user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.warning(f"⚠️ Subscription check failed (Bypassing): {e}")
        return True # السماح بالمرور لعدم تعليق البوت

# ===== 4. إرسال الفيديو النهائي (محرك الإرسال الآمن) =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    # محاولة تحديث البيانات من السورس
    try:
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if source_msg and source_msg.caption:
            title = clean_series_title(source_msg.caption)
            ep_match = re.search(r'(\d+)', source_msg.caption)
            if ep_match: ep = int(ep_match.group(1))
            db_query("UPDATE videos SET title=%s, ep_num=%s WHERE v_id=%s", (title, ep, v_id), fetch=False)
    except Exception as e:
        logging.error(f"⚠️ Error accessing source for sync: {e}")

    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    is_subscribed = await check_subscription(client, user_id)
    btns = await get_episodes_markup(title, v_id)
    
    safe_title = obfuscate_visual(escape(title))
    cap = (f"<b>📺 المسلسل : {safe_title}</b>\n"
           f"<b>🎞️ رقم الحلقة : {escape(str(ep))}</b>\n"
           f"<b>💿 الجودة : {escape(str(q))}</b>\n"
           f"<b>⏳ المدة : {escape(str(dur))}</b>\n\n🍿 <b>مشاهدة ممتعة نتمناها لكم!</b>")

    if not is_subscribed:
        cap += f"\n\n⚠️ <b>انضم للقناة لمتابعة الحلقات القادمة 👇</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام (مهم)", url=FORCE_SUB_LINK)]] + (btns if btns else []))
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    try:
        # استخدام copy_message مع تحديد من أين وإلى أين بدقة
        await client.copy_message(
            chat_id=chat_id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=cap,
            reply_markup=markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"❌ Final Send Failed: {e}")
        await client.send_message(chat_id, f"🎬 **{safe_title} - حلقة {ep}**\n\n⚠️ عذراً، تعذر نسخ الفيديو. تأكد من وجود البوت كأدمن في السورس.")

# ===== 5. أوامر الإدارة =====

@app.on_message(filters.command("clear") & (filters.user(ADMIN_ID) | filters.chat(SOURCE_CHANNEL)))
async def clear_handler(client, message):
    db_query("DELETE FROM videos WHERE status != 'posted'", fetch=False)
    await message.reply_text("✅ تم تنظيف العمليات غير المكتملة.")

@app.on_message(filters.command("del") & filters.user(ADMIN_ID))
async def delete_handler(client, message):
    full_text = message.text.replace("/del ", "", 1).strip()
    match = re.match(r'^(.+?)\s+(\d+)$', full_text)
    if match:
        title, ep = match.group(1).strip(), match.group(2)
        db_query("DELETE FROM videos WHERE title = %s AND ep_num = %s", (title, int(ep)), fetch=False)
        await message.reply_text(f"🗑️ تم حذف مسلسل {title} حلقة {ep}.")
    else:
        await message.reply_text("📝 ارسل: `/del اسم_المسلسل رقم_الحلقة`")

# ===== 6. استقبال وتجهيز الميديا =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or (message.document if message.document and "video" in message.document.mime_type else None)
    d = media.duration if media and hasattr(media, 'duration') else 0
    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو ({dur}). أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id, title = res[0][0], clean_series_title(message.caption or "")
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"),
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
    ]])
    await message.reply_text(f"📌 المسلسل: <b>{escape(title)}</b>\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_", 2)
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: <b>{q}</b>. أرسل الآن رقم الحلقة:")

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
    caption = f"🎬 <b>{safe_t}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n<b>الجودة: [{q}]</b>\n<b>المدة: [{dur}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")]])
    
    try:
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
        await message.reply_text("🚀 تم النشر في القناة بنجاح.")
    except Exception as e:
        await message.reply_text(f"❌ فشل النشر: {e}")

# ===== 7. أوامر المستخدم =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>! 👋")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        await message.reply_text("❌ الفيديو غير موجود أو تم حذفه.")

if __name__ == "__main__":
    init_db()
    app.run()
