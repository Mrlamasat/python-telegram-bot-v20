import os
import psycopg2
import logging
import re
import asyncio
import traceback
import time
from datetime import datetime
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

# ===== إعدادات التسجيل =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# ===== [1] الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # تأكد من وجود BOT_TOKEN في المتغيرات
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

# ===== [2] تعريف البوت =====
app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [3] متغيرات الحماية من FloodWait =====
last_request_time = {}
REQUEST_LIMIT = 3  # عدد الطلبات المسموح بها
TIME_WINDOW = 10   # خلال 10 ثواني

# ===== [4] معالج الحماية من FloodWait =====
@app.on_message(filters.private)
async def rate_limit_handler(client, message):
    """معالج الحد من الطلبات لحماية البوت من الضغط"""
    user_id = message.from_user.id
    current_time = time.time()
    
    # تنظيف السجلات القديمة
    if user_id in last_request_time:
        last_request_time[user_id] = [
            t for t in last_request_time[user_id] 
            if current_time - t < TIME_WINDOW
        ]
    else:
        last_request_time[user_id] = []
    
    # التحقق من عدد الطلبات
    if len(last_request_time[user_id]) >= REQUEST_LIMIT:
        wait_time = TIME_WINDOW - (current_time - last_request_time[user_id][0])
        if wait_time > 0:
            logging.warning(f"⚠️ مستخدم {user_id} تجاوز الحد، انتظر {wait_time:.0f} ثانية")
            await message.reply_text(
                f"⏳ أنت تطلب بسرعة كبيرة!\n"
                f"يرجى الانتظار {wait_time:.0f} ثانية ثم حاول مجدداً.\n"
                f"هذا لحماية البوت من الضغط العالي."
            )
            return  # منع الرسالة من المرور
    
    # تسجيل الطلب الحالي
    last_request_time[user_id].append(current_time)
    
    # السماح للرسالة بالمرور للمعالجات الأخرى
    # مهم: نعيد None لتكمل الرسالة طريقها
    return None

# ===== [5] دوال استخراج البيانات =====
def extract_episode_number(text):
    """استخراج رقم الحلقة من النص بذكاء"""
    if not text:
        return None
    
    text = text.strip()
    
    # قائمة الأنماط للبحث عن رقم الحلقة
    patterns = [
        # أنماط بالعربية
        r'[\[\(\{]?(\d+)[\]\)\}]?\s*[-\u2013]\s*(?:الحلقة|الحلقه|حلقة|حلقه|رقم الحلقة|رقم الحلقه)',
        r'(?:الحلقة|الحلقه|حلقة|حلقه|رقم الحلقة|رقم الحلقه)\s*[\[\(\{]?\s*(\d+)\s*[\]\)\}]?',
        r'[\[\(\{]?(\d+)[\]\)\}]?\s*[-\u2013]\s*(?:episode|ep|part)',
        r'(?:episode|ep|part)\s*[\[\(\{]?\s*(\d+)\s*[\]\)\}]?',
        r'[\[\(\{](\d+)[\]\)\}]',
        r'(?:حلقة|حلقه)\s*[:\-]?\s*(\d+)',
        r'.*?(\d+).*?',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                num = int(match.group(1))
                # التحقق من أن الرقم معقول (1-1000)
                if 1 <= num <= 1000:
                    logging.info(f"✅ تم استخراج رقم {num} من النص: {text[:50]}...")
                    return num
            except:
                continue
    
    # محاولة أخيرة: البحث عن أي رقم
    numbers = re.findall(r'\d+', text)
    if numbers:
        try:
            num = int(numbers[0])
            if 1 <= num <= 1000:
                logging.info(f"⚠️ تم استخراج رقم {num} كآخر خيار من النص: {text[:50]}...")
                return num
        except:
            pass
    
    logging.warning(f"❌ لم يتم العثور على رقم حلقة في النص: {text[:50]}...")
    return None

def extract_title(text):
    """استخراج عنوان المسلسل من النص"""
    if not text:
        return "فيديو"
    
    # إزالة أرقام الحلقات من النص للحصول على العنوان النظيف
    lines = text.split('\n')
    title = lines[0] if lines else text
    
    # إزالة أرقام الحلقات من السطر الأول
    title = re.sub(r'(?:الحلقة|الحلقه|حلقة|حلقه|episode|ep|part)\s*[:\-]?\s*\d+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[\[\(\{]\d+[\]\)\}]', '', title)
    title = re.sub(r'-\s*\d+\s*$', '', title)
    
    # تنظيف المسافات الزائدة
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'[-\s]+$', '', title)
    
    return title if title else "فيديو"

# ===== [6] دوال قاعدة البيانات =====
def init_database():
    """إنشاء الجداول المطلوبة في قاعدة البيانات"""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        
        # إنشاء جدول videos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                v_id TEXT PRIMARY KEY,
                title TEXT,
                ep_num INTEGER,
                poster_id TEXT,
                status TEXT DEFAULT 'waiting',
                views INTEGER DEFAULT 0,
                last_view TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # إنشاء جدول users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                joined_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # إنشاء جدول views_log
        cur.execute("""
            CREATE TABLE IF NOT EXISTS views_log (
                id SERIAL PRIMARY KEY,
                v_id TEXT,
                viewed_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ تم إنشاء/تأكيد جداول قاعدة البيانات")
    except Exception as e:
        logging.error(f"❌ فشل إنشاء الجداول: {e}")

def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            res = cur.fetchall()
        else:
            conn.commit()
            res = None
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return [] if fetch else None

# ===== [7] نظام الإصلاح الديناميكي =====
async def find_video_in_source(client, title, ep_num):
    """البحث عن الفيديو في قناة المصدر"""
    logging.info(f"🔍 البحث عن: {title} حلقة {ep_num}")
    
    async for msg in client.get_chat_history(SOURCE_CHANNEL, limit=500):
        if not (msg.video or msg.document):
            continue
            
        content = (msg.caption or msg.text or "").lower()
        
        # البحث عن التطابق
        title_lower = title.lower()
        
        # التحقق من وجود العنوان ورقم الحلقة
        if title_lower in content:
            # استخراج رقم الحلقة من محتوى الرسالة
            msg_ep = extract_episode_number(content)
            if msg_ep == ep_num:
                logging.info(f"✅ تم العثور على الفيديو: {msg.id}")
                return msg.id
    
    logging.warning(f"❌ لم يتم العثور على الفيديو")
    return None

async def show_episode(client, message, v_id):
    """عرض الحلقة مع محاولات متعددة"""
    try:
        # البحث في قاعدة البيانات
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not res:
            logging.warning(f"⚠️ المعرف {v_id} غير موجود في قاعدة البيانات")
            
            # محاولة البحث المباشر في القناة
            try:
                msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if msg and (msg.video or msg.document):
                    caption = msg.caption or msg.text or ""
                    
                    # استخراج رقم الحلقة
                    ep_num = extract_episode_number(caption) or 0
                    
                    # استخراج العنوان
                    title = extract_title(caption)
                    
                    # إدخال البيانات في قاعدة البيانات
                    db_query(
                        "INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title = EXCLUDED.title, ep_num = EXCLUDED.ep_num",
                        (v_id, title, ep_num),
                        fetch=False
                    )
                    
                    res = [(title, ep_num)]
                    logging.info(f"✅ تم استرداد البيانات: {title} - حلقة {ep_num}")
                else:
                    await message.reply_text("❌ لم يتم العثور على بيانات الحلقة.")
                    return
            except Exception as e:
                logging.error(f"❌ فشل البحث المباشر: {e}")
                await message.reply_text("❌ لم يتم العثور على بيانات الحلقة.")
                return
        
        title, ep = res[0]
        
        # التأكد من أن رقم الحلقة صحيح
        if ep == 0:
            logging.warning(f"⚠️ رقم الحلقة 0 للمعرف {v_id}، محاولة استخراجه مرة أخرى")
            
            # محاولة جلب الرسالة لاستخراج الرقم الصحيح
            try:
                msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if msg and (msg.video or msg.document):
                    caption = msg.caption or msg.text or ""
                    new_ep = extract_episode_number(caption)
                    if new_ep and new_ep != 0:
                        ep = new_ep
                        # تحديث قاعدة البيانات
                        db_query(
                            "UPDATE videos SET ep_num = %s WHERE v_id = %s",
                            (ep, v_id),
                            fetch=False
                        )
                        logging.info(f"✅ تم تحديث رقم الحلقة إلى {ep}")
            except:
                pass
        
        # محاولة إرسال الفيديو
        try:
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=SOURCE_CHANNEL,
                message_id=int(v_id),
                caption=f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)]])
            )
            
            # تحديث الإحصائيات
            db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
            db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (v_id,), fetch=False)
            
        except FloodWait as e:
            logging.warning(f"⚠️ FloodWait في الإرسال: {e.value} ثانية")
            await asyncio.sleep(e.value)
            # إعادة المحاولة مرة واحدة
            await show_episode(client, message, v_id)
            
    except FloodWait as e:
        logging.warning(f"⚠️ FloodWait: {e.value} ثانية")
        await asyncio.sleep(e.value)
        # إعادة المحاولة مرة واحدة
        await show_episode(client, message, v_id)
    except Exception as e:
        logging.error(f"❌ خطأ في show_episode: {e}")
        await message.reply_text("❌ حدث خطأ في عرض الحلقة")

# ===== [8] معالج قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    """معالج الرسائل من قناة المصدر"""
    
    try:
        # معالجة الفيديو أو المستند
        if message.video or message.document:
            v_id = str(message.id)
            caption = message.caption or ""
            
            # استخراج رقم الحلقة
            ep_num = extract_episode_number(caption)
            
            # استخراج العنوان
            title = extract_title(caption)
            
            # إدخال أو تحديث في قاعدة البيانات
            if ep_num:
                db_query(
                    "INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title = EXCLUDED.title, ep_num = EXCLUDED.ep_num",
                    (v_id, title, ep_num),
                    fetch=False
                )
                logging.info(f"✅ تم حفظ الفيديو {v_id}: {title} - حلقة {ep_num}")
            else:
                db_query(
                    "INSERT INTO videos (v_id, title, status) VALUES (%s, %s, 'waiting') ON CONFLICT (v_id) DO NOTHING",
                    (v_id, title),
                    fetch=False
                )
                logging.info(f"⏳ تم حفظ الفيديو {v_id} في حالة انتظار (لم نجد رقم حلقة)")
            
            await message.reply_text(f"✅ تم استلام فيديو {message.id}")
        
        # معالجة الصور (البوسترات)
        elif message.photo:
            # البحث عن آخر فيديو في حالة انتظار
            res = db_query(
                "SELECT v_id, title FROM videos WHERE status='waiting' ORDER BY created_at DESC LIMIT 1"
            )
            
            if res:
                v_id, current_title = res[0]
                caption = message.caption or current_title
                
                # استخراج رقم الحلقة من تعليق الصورة إذا وجد
                ep_num = extract_episode_number(caption)
                
                if ep_num:
                    # تحديث مع رقم الحلقة
                    db_query(
                        "UPDATE videos SET title=%s, ep_num=%s, poster_id=%s, status='posted' WHERE v_id=%s",
                        (caption, ep_num, message.photo.file_id, v_id),
                        fetch=False
                    )
                    
                    # إنشاء رابط المشاهدة
                    me = await client.get_me()
                    markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
                    ]])
                    
                    # النشر في القناة العامة
                    await client.send_photo(
                        PUBLIC_POST_CHANNEL,
                        message.photo.file_id,
                        f"🎬 <b>{caption}</b>\n<b>الحلقة: [{ep_num}]</b>",
                        reply_markup=markup
                    )
                    
                    logging.info(f"🚀 تم النشر مباشرة: {caption} حلقة {ep_num}")
                    await message.reply_text(f"🚀 تم النشر!")
                else:
                    # حفظ البوستر فقط
                    db_query(
                        "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s",
                        (caption, message.photo.file_id, v_id),
                        fetch=False
                    )
                    logging.info(f"🖼️ تم حفظ البوستر للفيديو {v_id}")
                    await message.reply_text(f"🖼️ تم حفظ البوستر لـ: {caption}")
        
        # معالجة النص (رقم الحلقة)
        elif message.text and message.text.isdigit():
            # البحث عن آخر فيديو في حالة await_ep
            res = db_query(
                "SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY created_at DESC LIMIT 1"
            )
            
            if res:
                v_id, title, p_id = res[0]
                ep_num = int(message.text)
                
                # تحديث قاعدة البيانات
                db_query(
                    "UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s",
                    (ep_num, v_id),
                    fetch=False
                )
                
                # إنشاء رابط المشاهدة
                me = await client.get_me()
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
                ]])
                
                # النشر في القناة العامة
                await client.send_photo(
                    PUBLIC_POST_CHANNEL,
                    p_id,
                    f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep_num}]</b>",
                    reply_markup=markup
                )
                
                logging.info(f"🚀 تم النشر: {title} حلقة {ep_num}")
                await message.reply_text(f"🚀 تم النشر!")
    
    except FloodWait as e:
        logging.warning(f"⚠️ FloodWait في معالج المصدر: {e.value} ثانية")
        await asyncio.sleep(e.value)
    except Exception as e:
        logging.error(f"❌ خطأ في handle_source: {e}")

# ===== [9] الأوامر الخاصة =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    try:
        # تسجيل المستخدم
        db_query(
            "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (message.from_user.id,),
            fetch=False
        )
        
        if len(message.command) > 1:
            # عرض الحلقة
            await show_episode(client, message, message.command[1])
        else:
            await message.reply_text(
                f"👋 أهلاً بك في بوت المسلسلات.\n"
                f"يمكنك مشاهدة الحلقات عبر الروابط المنشورة في القناة."
            )
    except FloodWait as e:
        logging.warning(f"⚠️ FloodWait: {e.value} ثانية")
        await asyncio.sleep(e.value)
    except Exception as e:
        logging.error(f"❌ خطأ في start_cmd: {e}")
        await message.reply_text("❌ حدث خطأ، يرجى المحاولة لاحقاً")

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        d24 = db_query("SELECT COUNT(*) FROM views_log WHERE viewed_at >= NOW() - INTERVAL '24 hours'")[0][0]
        u_count = db_query("SELECT COUNT(*) FROM users")[0][0]
        v_count = db_query("SELECT COUNT(*) FROM videos WHERE status='posted'")[0][0]
        zero_ep = db_query("SELECT COUNT(*) FROM videos WHERE ep_num IS NULL OR ep_num = 0")[0][0]
        
        await message.reply_text(
            f"📊 إحصائيات البوت:\n"
            f"👤 المشتركين: {u_count}\n"
            f"🎬 الفيديوهات: {v_count}\n"
            f"⚠️ بدون رقم حلقة: {zero_ep}\n"
            f"👁️ مشاهدات 24 ساعة: {d24}"
        )
    except Exception as e:
        logging.error(f"❌ خطأ في stats_command: {e}")
        await message.reply_text("❌ حدث خطأ في جلب الإحصائيات")

@app.on_message(filters.command("fix") & filters.private)
async def fix_command(client, message):
    """أمر يدوي لإصلاح قاعدة البيانات"""
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.reply_text("🔄 جاري فحص وإصلاح قاعدة البيانات...")
    
    try:
        # فحص جميع الفيديوهات برقم حلقة 0
        videos = db_query("SELECT v_id, title FROM videos WHERE ep_num IS NULL OR ep_num = 0")
        
        fixed_count = 0
        for v_id, title in videos:
            try:
                msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if msg and (msg.video or msg.document):
                    caption = msg.caption or msg.text or ""
                    ep_num = extract_episode_number(caption)
                    
                    if ep_num:
                        db_query(
                            "UPDATE videos SET ep_num = %s WHERE v_id = %s",
                            (ep_num, v_id),
                            fetch=False
                        )
                        fixed_count += 1
                        logging.info(f"✅ تم إصلاح رقم الحلقة للفيديو {v_id}: {ep_num}")
            except Exception as e:
                logging.error(f"❌ فشل إصلاح {v_id}: {e}")
        
        await message.reply_text(f"✅ تم إصلاح {fixed_count} فيديو")
    except Exception as e:
        logging.error(f"❌ خطأ في fix_command: {e}")
        await message.reply_text(f"❌ حدث خطأ: {e}")

@app.on_message(filters.command("fix_webhook") & filters.private)
async def fix_webhook_command(client, message):
    """أمر لإزالة الـ webhook"""
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.reply_text("🔄 جاري فحص وإزالة الـ webhook...")
    
    try:
        await client.delete_webhook()
        await message.reply_text("✅ تم إزالة الـ webhook بنجاح، أعد تشغيل البوت")
    except Exception as e:
        await message.reply_text(f"❌ فشل إزالة الـ webhook: {e}")

# ===== [10] الدالة الرئيسية =====
async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    try:
        # تهيئة قاعدة البيانات
        init_database()
        
        logging.info("🚀 بدء تشغيل البوت...")
        
        # تشغيل البوت
        await app.start()
        
        # إزالة أي webhook قديم
        try:
            await app.delete_webhook()
            logging.info("✅ تم إزالة الـ webhook")
        except:
            pass
        
        # تسجيل الدخول
        me = await app.get_me()
        logging.info(f"✅ البوت يعمل: @{me.username}")
        
        # إرسال إشعار للمسؤول
        try:
            await app.send_message(ADMIN_ID, "✅ البوت يعمل الآن مع نظام الحماية من الضغط")
        except:
            pass
        
        # البقاء قيد التشغيل
        await asyncio.Event().wait()
        
    except Exception as e:
        logging.error(f"❌ فشل تشغيل البوت: {e}")
        logging.error(traceback.format_exc())
    finally:
        await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("👋 تم إيقاف البوت يدوياً")
    except Exception as e:
        logging.error(f"❌ خطأ غير متوقع: {e}")
