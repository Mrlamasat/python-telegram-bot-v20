import os
import logging
import re
from html import escape
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

# ===== معرفات القنوات =====
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003554018307
FORCE_SUB_LINK = "https://t.me/+PyUeOtPN1fs0NDA0"
PUBLIC_POST_CHANNEL = "@ramadan2206"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Connection Pool =====
db_pool = pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode="require")

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

# ===== إنشاء الجداول تلقائياً =====
def init_db():
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
    logging.info("✅ Database initialized.")

# ===== الدوال المساعدة =====
def obfuscate_visual(text):
    if not text:
        return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text:
        return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def get_episodes_markup(title, current_v_id):
    res = db_query(
        "SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC",
        (title,)
    )
    if not res:
        return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps:
            continue
        seen_eps.add(ep_num)
        label = f"✅️ {ep_num}" if v_id == current_v_id else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

# ===== إرسال الفيديو النهائي =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    db_query(
        "UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s",
        (v_id,),
        fetch=False
    )
    btns = await get_episodes_markup(title, v_id)
    is_subscribed = await check_subscription(client, user_id)

    safe_title = obfuscate_visual(escape(title))
    info_text = (
        f"<b><a href='https://s6.gifyu.com/images/S6atp.gif'>&#8205;</a>📺 المسلسل : {safe_title}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6at3.gif'>&#8205;</a>🎞️ رقم الحلقة : {escape(str(ep))}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6atZ.gif'>&#8205;</a>💿 الجودة : {escape(str(q))}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6at7.gif'>&#8205;</a>⏳ المدة : {escape(str(dur))}</b>"
    )
    cap = f"{info_text}\n\n🍿 <b>مشاهدة ممتعة نتمناها لكم!</b>"

    if not is_subscribed:
        cap += "\n\n⚠️ <b>انضم للقناة البديلة لمتابعة الحلقات القادمة 👇</b>"
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 انضمام (مهم)", url=FORCE_SUB_LINK)]] + (btns if btns else [])
        )
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    try:
        await client.copy_message(
            chat_id, SOURCE_CHANNEL, int(v_id),
            caption=cap, parse_mode=ParseMode.HTML, reply_markup=markup
        )
    except Exception as e:
        logging.error(f"copy_message error: {e}")
        await client.send_message(chat_id, f"🎬 {safe_title} - حلقة {ep}")

# ===== أوامر الأدمن =====
@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    top = db_query(
        "SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 10"
    )
    text = "📊 <b>تقرير الأداء (الأكثر مشاهدة):</b>\n\n"
    if top:
        for i, r in enumerate(top, 1):
            text += f"{i}. 🎬 <b>{escape(r[0])}</b>\n└ حلقة {r[1]} ← 👤 <b>{r[2]} مشاهدة</b>\n\n"
    else:
        text += "لا توجد بيانات بعد."
    await message.reply_text(text, parse_mode=ParseMode.HTML)

# ===== استقبال الفيديو من قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    d = media.duration if media and hasattr(media, 'duration') else 0
    dur = f"{d // 3600:02}:{(d % 3600) // 60:02}:{d % 60:02}"
    db_query(
        "INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) "
        "ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s",
        (v_id, dur, dur),
        fetch=False
    )
    await message.reply_text(
        f"✅ تم استقبال الفيديو ({dur}).\nأرسل الآن صورة البوستر مع كابشن اسم المسلسل.",
        parse_mode=ParseMode.HTML
    )

# ===== استقبال البوستر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    # نجلب آخر فيديو بحالة waiting فقط
    res = db_query(
        "SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1"
    )
    if not res:
        await message.reply_text("⚠️ لا يوجد فيديو بانتظار البوستر.")
        return
    v_id = res[0][0]
    title = clean_series_title(message.caption)
    db_query(
        "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s",
        (title, message.photo.file_id, v_id),
        fetch=False
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"),
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
    ]])
    await message.reply_text(
        f"📌 المسلسل: <b>{escape(title)}</b>\nاختر جودة الفيديو:",
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )

# ===== اختيار الجودة =====
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    # نستخدم maxsplit=2 لتجنب مشكلة الـ underscore في الـ v_id
    parts = cb.data.split("_", 2)
    if len(parts) != 3:
        await cb.answer("بيانات غير صحيحة.", show_alert=True)
        return
    _, q, v_id = parts
    db_query(
        "UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s",
        (q, v_id),
        fetch=False
    )
    await cb.message.edit_text(
        f"✅ الجودة: <b>{q}</b>\nأرسل الآن رقم الحلقة (أرقام فقط):",
        parse_mode=ParseMode.HTML
    )
    await cb.answer()

# ===== استقبال رقم الحلقة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit():
        return
    res = db_query(
        "SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1"
    )
    if not res:
        return
    v_id, title, p_id, q, dur = res[0]
    ep_num = int(message.text)
    db_query(
        "UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s",
        (ep_num, v_id),
        fetch=False
    )

    b_info = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    caption = (
        f"🎬 <b>{safe_t}</b>\n\n"
        f"<b>الحلقة: [{ep_num}]</b>\n"
        f"<b>الجودة: [{q}]</b>\n"
        f"<b>المدة: [{dur}]</b>\n\n"
        f"نتمنى لكم مشاهدة ممتعة 🍿"
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")
    ]])

    try:
        await client.send_photo(
            PUBLIC_POST_CHANNEL, p_id,
            caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML
        )
        await message.reply_text("🚀 تم النشر في القناة العامة بنجاح ✅")
    except Exception as e:
        logging.error(f"send_photo error: {e}")
        await message.reply_text(f"❌ خطأ في النشر: {e}")

# ===== /start للمستخدمين =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(
            f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>! 👋\n"
            f"ابحث عن مسلسلك المفضل في قناتنا 📺",
            parse_mode=ParseMode.HTML
        )
        return

    v_id = message.command[1]
    res = db_query(
        "SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s AND status='posted'",
        (v_id,)
    )
    if not res:
        await message.reply_text("⚠️ الحلقة غير موجودة أو لم تُنشر بعد.")
        return

    await send_video_final(
        client, message.chat.id, message.from_user.id, v_id, *res[0]
    )

# ===== التشغيل =====
if __name__ == "__main__":
    init_db()
    logging.info("🤖 البوت يعمل الآن...")
    app.run()
