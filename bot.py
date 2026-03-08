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
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

# ===== [2] تعريف البوت =====
app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [3] دوال قاعدة البيانات =====
def init_database():
    """إنشاء الجداول المطلوبة في قاعدة البيانات"""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        
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
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                joined_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
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
        logging.info("✅ تم إنشاء جداول قاعدة البيانات")
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

# ===== [4] دوال استخراج البيانات =====
def extract_episode_number(text):
    """استخراج رقم الحلقة من النص"""
    if not text:
        return None
    
    text = text.strip()
    
    patterns = [
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
                if 1 <= num <= 1000:
                    return num
            except:
                continue
    
    numbers = re.findall(r'\d+', text)
    if numbers:
        try:
            return int(numbers[0])
        except:
            pass
    
    return None

def extract_title(text):
    """استخراج عنوان المسلسل من النص"""
    if not text:
        return "فيديو"
    
    lines = text.split('\n')
    title = lines[0] if lines else text
    
    title = re.sub(r'(?:الحلقة|الحلقه|حلقة|حلقه|episode|ep|part)\s*[:\-]?\s*\d+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[\[\(\{]\d+[\]\)\}]', '', title)
    title = re.sub(r'-\s*\d+\s*$', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title if title else "فيديو"

# ===== [5] معالج فحص صلاحيات البوت =====
@app.on_message(filters.command("check") & filters.private)
async def check_bot_permissions(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.reply_text("🔍 جاري فحص صلاحيات البوت...")
    
    try:
        report = "📊 **تقرير صلاحيات البوت:**\n\n"
        
        # فحص قناة المصدر
        try:
            source_chat = await client.get_chat(SOURCE_CHANNEL)
            source_member = await client.get_chat_member(SOURCE_CHANNEL, "me")
            report += f"**قناة المصدر:** {source_chat.title}\n"
            report += f"- المعرف: `{SOURCE_CHANNEL}`\n"
            report += f"- هل البوت عضو: {'✅' if source_member else '❌'}\n"
            report += f"- صلاحية البوت: {source_member.status if source_member else '❌'}\n\n"
        except Exception as e:
            report += f"**قناة المصدر:** ❌ فشل الوصول\n"
            report += f"- الخطأ: {str(e)[:100]}\n\n"
        
        # فحص قناة النشر
        try:
            public_chat = await client.get_chat(PUBLIC_POST_CHANNEL)
            public_member = await client.get_chat_member(PUBLIC_POST_CHANNEL, "me")
            report += f"**قناة النشر:** {public_chat.title}\n"
            report += f"- المعرف: `{PUBLIC_POST_CHANNEL}`\n"
            report += f"- هل البوت عضو: {'✅' if public_member else '❌'}\n"
            report += f"- صلاحية البوت: {public_member.status if public_member else '❌'}\n\n"
        except Exception as e:
            report += f"**قناة النشر:** ❌ فشل الوصول\n"
            report += f"- الخطأ: {str(e)[:100]}\n\n"
        
        # فحص اتصال قاعدة البيانات
        try:
            db_test = db_query("SELECT 1")
            report += f"**قاعدة البيانات:** ✅ متصلة\n"
        except:
            report += f"**قاعدة البيانات:** ❌ غير متصلة\n"
        
        await message.reply_text(report, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ في الفحص: {e}")

# ===== [6] معالج اختبار بسيط =====
@app.on_message(filters.private & filters.text)
async def test_handler(client, message):
    # تجاهل الأوامر
    if message.text.startswith('/'):
        return
    
    await message.reply_text(
        f"✅ البوت يعمل!\n"
        f"رسالتك: {message.text}\n\n"
        f"لجلب حلقة استخدم رابط من القناة\n"
        f"أو استخدم /check لفحص الصلاحيات"
    )

# ===== [7] معالج قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    """معالج الرسائل من قناة المصدر"""
    try:
        if message.video or message.document:
            v_id = str(message.id)
            caption = message.caption or ""
            
            ep_num = extract_episode_number(caption)
            title = extract_title(caption)
            
            if ep_num:
                db_query(
                    "INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title = EXCLUDED.title, ep_num = EXCLUDED.ep_num",
                    (v_id, title, ep_num),
                    fetch=False
                )
                logging.info(f"✅ تم حفظ الفيديو {v_id}: {title} - حلقة {ep_num}")
            
            await message.reply_text(f"✅ تم استلام فيديو {message.id}")
        
        elif message.photo:
            res = db_query(
                "SELECT v_id, title FROM videos WHERE status='waiting' ORDER BY created_at DESC LIMIT 1"
            )
            
            if res:
                v_id, current_title = res[0]
                caption = message.caption or current_title
                ep_num = extract_episode_number(caption)
                
                if ep_num:
                    db_query(
                        "UPDATE videos SET title=%s, ep_num=%s, poster_id=%s, status='posted' WHERE v_id=%s",
                        (caption, ep_num, message.photo.file_id, v_id),
                        fetch=False
                    )
                    
                    me = await client.get_me()
                    markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
                    ]])
                    
                    await client.send_photo(
                        PUBLIC_POST_CHANNEL,
                        message.photo.file_id,
                        f"🎬 <b>{caption}</b>\n<b>الحلقة: [{ep_num}]</b>",
                        reply_markup=markup
                    )
                    
                    logging.info(f"🚀 تم النشر: {caption} حلقة {ep_num}")
                    await message.reply_text(f"🚀 تم النشر!")
                else:
                    db_query(
                        "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s",
                        (caption, message.photo.file_id, v_id),
                        fetch=False
                    )
                    await message.reply_text(f"🖼️ تم حفظ البوستر لـ: {caption}")
        
        elif message.text and message.text.isdigit():
            res = db_query(
                "SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY created_at DESC LIMIT 1"
            )
            
            if res:
                v_id, title, p_id = res[0]
                ep_num = int(message.text)
                
                db_query(
                    "UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s",
                    (ep_num, v_id),
                    fetch=False
                )
                
                me = await client.get_me()
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
                ]])
                
                await client.send_photo(
                    PUBLIC_POST_CHANNEL,
                    p_id,
                    f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep_num}]</b>",
                    reply_markup=markup
                )
                
                logging.info(f"🚀 تم النشر: {title} حلقة {ep_num}")
                await message.reply_text(f"🚀 تم النشر!")
    
    except Exception as e:
        logging.error(f"❌ خطأ في handle_source: {e}")

# ===== [8] أمر start =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    try:
        db_query(
            "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (message.from_user.id,),
            fetch=False
        )
        
        if len(message.command) > 1:
            v_id = message.command[1]
            
            # محاولة جلب الفيديو
            try:
                msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if msg and (msg.video or msg.document):
                    caption = msg.caption or msg.text or ""
                    ep_num = extract_episode_number(caption) or 0
                    title = extract_title(caption)
                    
                    await client.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=SOURCE_CHANNEL,
                        message_id=int(v_id),
                        caption=f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep_num}</b>",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)
                        ]])
                    )
                    
                    db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
                else:
                    await message.reply_text("❌ لم يتم العثور على الحلقة")
            except Exception as e:
                await message.reply_text(f"❌ خطأ: {e}")
        else:
            await message.reply_text(
                f"👋 أهلاً بك في بوت المسلسلات.\n"
                f"يمكنك مشاهدة الحلقات عبر الروابط المنشورة في القناة.\n"
                f"استخدم /check لفحص صلاحيات البوت"
            )
    except Exception as e:
        logging.error(f"❌ خطأ في start_cmd: {e}")

# ===== [9] الدالة الرئيسية =====
async def main():
    try:
        init_database()
        
        logging.info("🚀 بدء تشغيل البوت...")
        await app.start()
        
        try:
            await app.delete_webhook()
            logging.info("✅ تم إزالة الـ webhook")
        except:
            pass
        
        me = await app.get_me()
        logging.info(f"✅ البوت يعمل: @{me.username}")
        
        # إشعار للمسؤول
        try:
            await app.send_message(ADMIN_ID, "✅ البوت يعمل الآن - استخدم /check لفحص الصلاحيات")
        except:
            pass
        
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
        logging.info("👋 تم إيقاف البوت")
    except Exception as e:
        logging.error(f"❌ خطأ: {e}")
