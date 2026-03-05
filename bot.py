import os
import logging
import re
import asyncio
from html import escape
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from pyrogram.enums import ParseMode

# ===== الإعدادات الأساسية (تأكد من ضبطها في Railway) =====
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

logging.basicConfig(level=logging.INFO)

# ===== Connection Pool لإدارة قاعدة البيانات =====
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

# ===== إنشاء الجداول وتحديث الهيكل =====
def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            quality TEXT DEFAULT 'HD',
            ep_num INTEGER DEFAULT 0,
            duration TEXT DEFAULT '00:00:00',
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            raw_caption TEXT
        )
    """, fetch=False)
    logging.info("✅ Database initialized.")

# ===== الدوال المساعدة (التنظيف والعرض) =====
def obfuscate_visual(text):
    return " . ".join(list(text)) if text else ""

def clean_series_title(text):
    if not text: return "مسلسل"
    # حذف نصوص الجودة والروابط والرموز
    text = re.sub(r'(الجودة|المدة|سنة العرض|✨|⏱|HD|📥|💿).*', '', text, flags=re.I)
    # حذف كلمة الحلقة والأرقام
    text = re.sub(r'(الحلقة|حلقة|#|EP)?\s*\d+', '', text, flags=re.I)
    return text.strip(" :-|")

async def get_episodes_markup(title, current_v_id):
    res = db_query(
        "SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC",
        (title,)
    )
    if not res: return None
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅️ {ep_num}" if v_id == current_v_id else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup(buttons)

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# ===== معالج الأرشفة التلقائية (للقديم) =====
@app.on_message(filters.command("sync_old") & filters.user(ADMIN_ID))
async def sync_old_cmd(client, message):
    if len(message.command) < 3:
        return await message.reply("⚠️ استخدم: `/sync_old 1 3025`")
    
    start, end = int(message.command[1]), int(message.command[2])
    m = await message.reply("🔄 جاري سحب البيانات القديمة وتحويلها لنظام الأزرار...")
    
    count = 0
    for msg_id in range(start, end + 1):
        try:
            msg = await client.get_messages(SOURCE_CHANNEL, msg_id)
            if msg and (msg.video or msg.document):
                title = clean_series_title(msg.caption)
                nums = re.findall(r'\d+', msg.caption or "")
                ep = int(nums[-1]) if nums else 0
                
                db_query("""
                    INSERT INTO videos (v_id, title, ep_num, status, raw_caption) 
                    VALUES (%s, %s, %s, 'posted', %s)
                    ON CONFLICT (v_id) DO UPDATE SET status='posted', title=EXCLUDED.title
                """, (str(msg_id), title, ep, msg.caption or ""), fetch=False)
                count += 1
            if msg_id % 100 == 0:
                await m.edit(f"⏳ معالجة المعرف {msg_id}.. مؤرشف: {count}")
        except: continue
    await m.edit(f"✅ تم بنجاح! مؤرشف {count} حلقة قديمة.")

# ===== استقبال الفيديوهات الجديدة (نظامك اليدوي) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.document
    d = media.duration if hasattr(media, 'duration') else 0
    dur = f"{d // 3600:02}:{(d % 3600) // 60:02}:{d % 60:02}"
    
    db_query(
        "INSERT INTO videos (v_id, status, duration, raw_caption) VALUES (%s, 'waiting', %s, %s) "
        "ON CONFLICT (v_id) DO UPDATE SET status='waiting'",
        (v_id, dur, message.caption or ""), fetch=False
    )
    await message.reply_text(f"✅ استقبلت الفيديو ({dur}).\nأرسل الآن **صورة البوستر** مع اسم المسلسل.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    
    v_id = res[0][0]
    title = clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_q' WHERE v_id=%s",
             (title, message.photo.file_id, v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"),
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
    ]])
    await message.reply_text(f"📌 المسلسل: {title}\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_", 2)
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}\nأرسل الآن **رقم الحلقة** (أرقام فقط):")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "sync_old"]))
async def receive_ep(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    
    v_id, title, p_id, q, dur = res[0]
    ep = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep, v_id), fetch=False)
    
    bot = await client.get_me()
    pub_cap = f"🎬 <b>{obfuscate_visual(title)}</b>\n\n<b>الحلقة: [{ep}]</b>\n<b>الجودة: [{q}]</b>\n\n🍿 مشاهدة ممتعة!"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{bot.username}?start={v_id}")]])
    
    await client.send_photo(PUBLIC_POST_CHANNEL, p_id, caption=pub_cap, reply_markup=markup)
    await message.reply_text("🚀 تم النشر بنجاح!")

# ===== نظام العرض للمستخدمين (Start) =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"مرحباً بك {message.from_user.first_name} 👋\nابحث عن حلقاتك هنا!")

    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if not res: return await message.reply_text("⚠️ غير موجود.")

    title, ep, q, dur = res[0]
    markup = await get_episodes_markup(title, v_id)
    is_sub = await check_subscription(client, message.from_user.id)
    
    cap = f"<b>📺 المسلسل: {obfuscate_visual(title)}</b>\n<b>🎞️ الحلقة: {ep}</b>\n<b>💿 الجودة: {q}</b>"
    if not is_sub:
        cap += "\n\n⚠️ انضم للقناة لمشاهدة الحلقة 👇"
        join_btn = [InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]
        markup = InlineKeyboardMarkup([join_btn] + (markup.inline_keyboard if markup else []))

    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=markup)

if __name__ == "__main__":
    init_db()
    app.run()
