import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ===== الإعدادات =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# المعرفات (تأكد أنها مطابقة لقنواتك)
SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307 
FORCE_SUB_CHANNEL = -1003894735143 

# التحقق من البيانات المطلوبة
if not all([API_ID, API_HASH, BOT_TOKEN, DATABASE_URL]):
    logger.error("❌ خطأ: تأكد من تعيين جميع متغيرات البيئة المطلوبة!")
    exit(1)

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دوال قاعدة البيانات =====
def init_database():
    """إنشء جداول قاعدة البيانات إذا لم تكن موجودة"""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                v_id VARCHAR(50) PRIMARY KEY,
                title VARCHAR(255),
                poster_id VARCHAR(255),
                duration VARCHAR(20),
                quality VARCHAR(10),
                ep_num VARCHAR(10),
                status VARCHAR(50) DEFAULT 'waiting',
                post_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")

def db_query(query, params=(), fetch=True):
    """تنفيذ استعلام في قاعدة البيانات مع معالجة الأخطاء"""
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
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
        logger.error(f"❌ خطأ في قاعدة البيانات: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def obfuscate_visual(text):
    """تنسيق النص بإضافة نقاط بين الأحرف"""
    if not text:
        return ""
    return " . ".join(list(text.replace(" ", "  ")))

def format_duration(seconds):
    """تحويل الثواني إلى صيغة HH:MM:SS"""
    if not seconds:
        return "00:00:00"
    try:
        s = int(seconds)
        hours = s // 3600
        minutes = (s % 3600) // 60
        secs = s % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    except:
        return "00:00:00"

def is_valid_episode_number(text):
    """التحقق من صحة رقم الحلقة"""
    if not text:
        return False
    return text.strip().isdigit()

# ===== 1. استقبال الفيديو (بداية العملية) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    try:
        v_id = str(message.id)
        
        # الحصول على المدة
        media = message.video or message.animation or message.document
        duration_seconds = 0
        
        if hasattr(media, 'duration') and media.duration:
            duration_seconds = media.duration
        
        dur = format_duration(duration_seconds)
        
        # حفظ في قاعدة البيانات
        db_query(
            """INSERT INTO videos (v_id, status, duration) 
               VALUES (%s, 'waiting', %s) 
               ON CONFLICT (v_id) 
               DO UPDATE SET status='waiting', duration=%s""",
            (v_id, dur, dur),
            fetch=False
        )
        
        logger.info(f"✅ تم استلام فيديو: {v_id}")
        
        await message.reply_text(
            f"✅ تم استلام الملف بنجاح.\n"
            f"⏳ المدة: {dur}\n\n"
            f"<b>الآن أرسل البوستر (الصورة) واكتب اسم المسلسل في وصفها.</b>",
            quote=True
        )
    except Exception as e:
        logger.error(f"❌ خطأ في receive_video: {e}")
        await message.reply_text(f"❌ حدث خطأ: {e}", quote=True)

# ===== 2. استقبال البوستر (الخطوة الثانية) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    try:
        # البحث عن آخر فيديو ينتظر بوستر
        res = db_query(
            "SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1"
        )
        
        if not res:
            await message.reply_text(
                "⚠️ لا يوجد فيديو في انتظار البوستر. أرسل فيديو أولاً!",
                quote=True
            )
            return
        
        v_id = res[0][0]
        title = message.caption
        
        if not title or not title.strip():
            await message.reply_text(
                "⚠️ خطأ: يجب كتابة اسم المسلسل في وصف الصورة (Caption) لكي أستمر!",
                quote=True
            )
            return
        
        title = title.strip()
        
        # حفظ البوستر والعنوان
        db_query(
            """UPDATE videos 
               SET title=%s, poster_id=%s, status='awaiting_quality', updated_at=CURRENT_TIMESTAMP 
               WHERE v_id=%s""",
            (title, message.photo.file_id, v_id),
            fetch=False
        )
        
        logger.info(f"✅ تم استقبال البوستر للفيديو: {v_id}")
        
        # اختيار الجودة
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"),
                InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
                InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
            ]
        ])
        
        await message.reply_text(
            f"📌 تم اعتماد الاسم: <b>{escape(title)}</b>\n\n"
            f"<b>اختر الجودة المطلوبة الآن:</b>",
            reply_markup=markup,
            quote=True
        )
    except Exception as e:
        logger.error(f"❌ خطأ في receive_poster: {e}")
        await message.reply_text(f"❌ حدث خطأ: {e}", quote=True)

# ===== 3. اختيار الجودة (الخطوة الثالثة) =====
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    try:
        data = cb.data.split("_")
        
        if len(data) < 3:
            await cb.answer("❌ خطأ في البيانات", show_alert=True)
            return
        
        quality = data[1]
        v_id = data[2]
        
        # التحقق من وجود الفيديو
        res = db_query("SELECT status FROM videos WHERE v_id=%s", (v_id,))
        
        if not res:
            await cb.answer("❌ لم يتم العثور على الفيديو", show_alert=True)
            return
        
        # تحديث الجودة
        db_query(
            """UPDATE videos 
               SET quality=%s, status='awaiting_ep', updated_at=CURRENT_TIMESTAMP 
               WHERE v_id=%s""",
            (quality, v_id),
            fetch=False
        )
        
        logger.info(f"✅ تم اختيار الجودة {quality} للفيديو: {v_id}")
        
        await cb.message.edit_text(
            f"✅ اخترت جودة: <b>{quality}</b>\n\n"
            f"<b>أرسل الآن رقم الحلقة فقط (مثلاً: 15):</b>"
        )
        await cb.answer("✅ تم تحديث الجودة")
        
    except Exception as e:
        logger.error(f"❌ خطأ في set_quality: {e}")
        await cb.answer(f"❌ حدث خطأ: {e}", show_alert=True)

# ===== 4. استقبال رقم الحلقة والنشر (الخطوة الأخيرة) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text)
async def receive_ep_num(client, message):
    try:
        if not is_valid_episode_number(message.text):
            return  # تجاهل الرسائل التي ليست أرقام
        
        ep_num = message.text.strip()
        
        # البحث عن آخر فيديو ينتظر رقم الحلقة
        res = db_query(
            """SELECT v_id, title, poster_id, quality, duration 
               FROM videos 
               WHERE status='awaiting_ep' 
               ORDER BY v_id DESC LIMIT 1"""
        )
        
        if not res:
            await message.reply_text(
                "⚠️ لا يوجد فيديو في انتظار رقم الحلقة. أكمل الخطوات السابقة أولاً!",
                quote=True
            )
            return
        
        v_id, title, p_id, quality, dur = res[0]
        
        # تنسيق الاسم بالنقاط
        safe_title = obfuscate_visual(escape(title))
        
        caption = (
            f"🎬 <b>{safe_title}</b>\n\n"
            f"<b>الحلقة:</b> [{ep_num}]\n"
            f"<b>الجودة:</b> [{quality}]\n"
            f"<b>المدة:</b> [{dur}]\n\n"
            f"نتمنى لكم مشاهدة ممتعة."
        )
        
        me = await client.get_me()
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]
        ])
        
        # النشر في القناة العامة
        post = await client.send_photo(
            chat_id=PUBLIC_POST_CHANNEL,
            photo=p_id,
            caption=caption,
            reply_markup=markup
        )
        
        # تحديث الحالة وحفظ ID المنشور
        db_query(
            """UPDATE videos 
               SET ep_num=%s, status='posted', post_id=%s, updated_at=CURRENT_TIMESTAMP 
               WHERE v_id=%s""",
            (ep_num, post.id, v_id),
            fetch=False
        )
        
        logger.info(f"🚀 تم نشر الحلقة {ep_num} من {title}")
        
        await message.reply_text(
            f"🚀 تم النشر بنجاح في القناة!\n\n"
            f"<b>المسلسل:</b> {escape(title)}\n"
            f"<b>الحلقة:</b> {ep_num}\n"
            f"<b>الجودة:</b> {quality}",
            quote=True
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في receive_ep_num: {e}")
        await message.reply_text(f"❌ فشل النشر: {e}", quote=True)

# ===== معالج الأخطاء =====
@app.on_message()
async def handle_errors(client, message):
    """معالج افتراضي لأي رسائل غير متوقعة"""
    pass

# ===== تشغيل البوت =====
async def main():
    """دالة البدء الرئيسية"""
    try:
        init_database()  # تهيئة قاعدة البيانات
        logger.info("🚀 جاري تشغيل البوت...")
        await app.start()
        logger.info("✅ البوت يعمل بنجاح")
        await app.idle()
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل البوت: {e}")
    finally:
        await app.stop()
        logger.info("🛑 تم إيقاف البوت")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
