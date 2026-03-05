import os
import psycopg2
import psycopg2.pool
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الأساسية (تأكد من وضعها في Railway Variables) =====
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

# ===== إدارة قاعدة البيانات =====
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
    logging.info("✅ تم تهيئة قاعدة البيانات بنجاح.")

# ===== نظام الجلب الذكي والأرشفة =====

async def get_or_archive_video(v_id):
    """دالة تبحث في القاعدة، وإذا لم تجد الفيديو تجلبه من القناة المصدر وتؤرشفه"""
    # البحث في القاعدة أولاً
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    
    if res:
        return res[0]
    
    # إذا لم يوجد (رابط قديم)، نحاول جلب المعلومات من القناة المصدر
    try:
        msg = await app.get_messages(SOURCE_CHANNEL, int(v_id))
        if msg and (msg.video or msg.document):
            # استخراج البيانات من الكابشن (الوصف)
            caption = msg.caption or "مسلسل غير معروف"
            title = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', caption).strip()
            ep_match = re.search(r'(\d+)', caption)
            ep = int(ep_match.group(1)) if ep_match else 0
            dur = "00:00:00"
            if msg.video:
                d = msg.video.duration
                dur = f"{d // 3600:02}:{(d % 3600) // 60:02}:{d % 60:02}"
            
            # أرشفة فورية في قاعدة البيانات
            db_query(
                "INSERT INTO videos (v_id, title, ep_num, quality, duration, status) VALUES (%s, %s, %s, %s, %s, %s)",
                (v_id, title, ep, "HD", dur, "posted"), fetch=False
            )
            logging.info(f"📦 تم أرشفة حلقة قديمة تلقائياً: {v_id}")
            return (title, ep, "HD", dur)
    except Exception as e:
        logging.error(f"❌ فشل جلب الحلقة القديمة {v_id}: {e}")
    
    return None

# ===== معالج الأوامر =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>! 👋\nارسل فيديو في قناة المصدر لنشره.")
        return

    v_id = message.command[1]
    user_id = message.from_user.id
    
    # التحقق من الاشتراك الإجباري
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in ["left", "kicked"]: raise Exception()
    except:
        return await message.reply_text(
            "⚠️ **يجب عليك الاشتراك في القناة أولاً لمشاهدة الحلقة!**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 اضغط هنا للاشتراك", url=FORCE_SUB_LINK)]])
        )

    # الجلب الذكي
    video_data = await get_or_archive_video(v_id)
    
    if video_data:
        title, ep, q, dur = video_data
        cap = (
            f"<b>📺 المسلسل : {escape(title)}</b>\n"
            f"<b>🎞️ رقم الحلقة : {ep}</b>\n"
            f"<b>💿 الجودة : {q}</b>\n"
            f"<b>⏳ المدة : {dur}</b>\n\n"
            f"🍿 <b>مشاهدة ممتعة!</b>"
        )
        
        # إرسال الفيديو من القناة المصدر
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=cap,
            parse_mode=ParseMode.HTML
        )
        # تحديث المشاهدات
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        await message.reply_text("❌ عذراً، هذه الحلقة غير موجودة حالياً.")

# ===== استقبال ونشر الفيديو الجديد (نفس منطقك السابق مع تحسين) =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.document
    d = getattr(media, 'duration', 0) if media else 0
    dur = f"{d // 3600:02}:{(d % 3600) // 60:02}:{d % 60:02}"
    
    db_query(
        "INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting'",
        (v_id, dur), fetch=False
    )
    await message.reply_text(f"✅ تم استلام الفيديو. أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    
    title = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', message.caption or "مسلسل").strip()
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='posted' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    # نشر مباشر في القناة العامة
    bot = await client.get_me()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{bot.username}?start={v_id}")]])
    
    await client.send_photo(
        chat_id=PUBLIC_POST_CHANNEL,
        photo=message.photo.file_id,
        caption=f"🎬 <b>{title}</b>\n\nاضغط على الزر أدناه للمشاهدة 👇",
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )
    await message.reply_text("🚀 تم النشر والأرشفة بنجاح.")

# تشغيل
if __name__ == "__main__":
    init_db()
    app.run()
