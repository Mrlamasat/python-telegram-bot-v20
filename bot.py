import os
import psycopg2
import psycopg2.pool
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعدادات التسجيل لمراقبة العمليات في Railway
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الأساسية =====
# تأكد من إضافة هذه القيم في قسم Variables في Railway
API_ID = int(os.environ.get("API_ID", "24803515"))
API_HASH = os.environ.get("API_HASH", "86414909a34199f18742f1b490f892cc")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHrgUVKh0D45SMa0iHYI-DkbuWxeYm-rns")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة اتصال قاعدة البيانات =====
db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = db_pool.getconn()
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
        if conn: db_pool.putconn(conn)

def init_db():
    # ملاحظة: DROP TABLE لضمان إصلاح خطأ column duration does not exist
    # بعد أول تشغيل ناجح، يمكنك إزالة سطر DROP TABLE للمحافظة على البيانات
    db_query("DROP TABLE IF EXISTS videos CASCADE", fetch=False)
    
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
    logging.info("✅ تم تهيئة قاعدة البيانات بنجاح مع كافة الأعمدة المطلوبة.")

# ===== نظام الجلب الذكي (للحلقات المحذوفة من القاعدة) =====

async def get_smart_video(v_id):
    """تبحث في القاعدة، وإذا لم تجد الفيديو تجلبه من المصدر وتؤرشفه فوراً"""
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        return res[0]
    
    # محاولة جلب "حي" من القناة المصدر (أرشفة تلقائية)
    try:
        msg = await app.get_messages(SOURCE_CHANNEL, int(v_id))
        if msg and (msg.video or msg.document):
            cap = msg.caption or "مسلسل"
            title = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', cap).strip()
            ep_match = re.search(r'(\d+)', cap)
            ep = int(ep_match.group(1)) if ep_match else 0
            dur = "00:00:00"
            if msg.video:
                d = msg.video.duration
                dur = f"{d // 3600:02}:{(d % 3600) // 60:02}:{d % 60:02}"
            
            # حفظ في القاعدة فوراً ليكون متاحاً المرة القادمة
            db_query(
                "INSERT INTO videos (v_id, title, ep_num, quality, duration, status) VALUES (%s, %s, %s, %s, %s, %s)",
                (v_id, title, ep, "HD", dur, "posted"), fetch=False
            )
            return (title, ep, "HD", dur)
    except:
        pass
    return None

# ===== معالجات الرسائل (Handlers) =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"مرحباً بك يا <b>{escape(message.from_user.first_name)}</b>! 👋\nارسل فيديو في قناة المصدر لنشره.")
        return

    v_id = message.command[1]
    
    # التحقق من الاشتراك الإجباري
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        if member.status in ["left", "kicked"]: raise Exception()
    except:
        return await message.reply_text(
            "⚠️ <b>عذراً، يجب عليك الاشتراك في القناة أولاً لمشاهدة الحلقة!</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 اضغط هنا للاشتراك", url=FORCE_SUB_LINK)]])
        )

    # جلب الفيديو (من القاعدة أو الأرشفة الذكية)
    video_data = await get_smart_video(v_id)
    if video_data:
        title, ep, q, dur = video_data
        cap = (
            f"<b>📺 المسلسل : {escape(title)}</b>\n"
            f"<b>🎞️ رقم الحلقة : {ep}</b>\n"
            f"<b>💿 الجودة : {q}</b>\n"
            f"<b>⏳ المدة : {dur}</b>\n\n"
            f"🍿 <b>مشاهدة ممتعة!</b>"
        )
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, parse_mode=ParseMode.HTML)
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        await message.reply_text("❌ لم يتم العثور على هذه الحلقة.")

# ===== استقبال ونشر الفيديو الجديد =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.document
    d = getattr(media, 'duration', 0) if media else 0
    dur = f"{d // 3600:02}:{(d % 3600) // 60:02}:{d % 60:02}"
    
    db_query(
        "INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s",
        (v_id, dur, dur), fetch=False
    )
    await message.reply_text(f"✅ تم استلام المرفق ({dur}). أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    
    title = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', message.caption or "مسلسل").strip()
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='posted' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    bot = await client.get_me()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{bot.username}?start={v_id}")]])
    
    await client.send_photo(
        chat_id=PUBLIC_POST_CHANNEL,
        photo=message.photo.file_id,
        caption=f"🎬 <b>{title}</b>\n\nاضغط على الزر أدناه للمشاهدة 👇",
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )
    await message.reply_text("🚀 تم النشر بنجاح.")

if __name__ == "__main__":
    init_db()
    app.run()
