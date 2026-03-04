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

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دوال قاعدة البيانات =====
def init_database():
    """تهيئة الجداول عند التشغيل"""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("✅ Database Initialized")
    except Exception as e:
        logger.error(f"❌ Database Init Error: {e}")

def db_query(query, params=(), fetch=True):
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
        logger.error(f"❌ Query Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()

def obfuscate_visual(text):
    """تنسيق الاسم بالتنقيط"""
    if not text: return ""
    return " . ".join(list(text.replace(" ", "  ")))

# ===== 1. استقبال الفيديو (المصدر) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') and media.duration else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    
    db_query(
        "INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s",
        (v_id, dur, dur), fetch=False
    )
    await message.reply_text(f"✅ تم استلام الملف ({dur}).\n**أرسل البوستر الآن واكتب اسم المسلسل في وصفه.**", quote=True)

# ===== 2. استقبال البوستر (المصدر) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY created_at DESC LIMIT 1")
    if not res:
        return

    v_id = res[0][0]
    title = message.caption
    if not title:
        await message.reply_text("⚠️ خطأ: يجب كتابة اسم المسلسل في وصف الصورة!", quote=True)
        return

    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), 
         InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), 
         InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]
    ])
    await message.reply_text(f"📌 الاسم: {title}\n**اختر الجودة:**", reply_markup=markup, quote=True)

# ===== 3. اختيار الجودة (Callback) =====
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}\n**أرسل رقم الحلقة الآن:**")

# ===== 4. رقم الحلقة والنشر النهائي =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text)
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY created_at DESC LIMIT 1")
    if not res: return
    
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text
    
    safe_title = obfuscate_visual(escape(title))
    caption = (
        f"🎬 <b>{safe_title}</b>\n\n"
        f"الحلقة: [{ep_num}]\n"
        f"الجودة: [{q}]\n"
        f"المدة: [{dur}]\n\n"
        f"نتمنى لكم مشاهدة ممتعة."
    )
    
    me = await client.get_me()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    try:
        post = await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
        db_query("UPDATE videos SET ep_num=%s, status='posted', post_id=%s WHERE v_id=%s", (ep_num, post.id, v_id), fetch=False)
        await message.reply_text(f"🚀 تم النشر بنجاح: {title}")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== 5. تحديث القناة عند تعديل البوستر في المصدر =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def handle_edit(client, message):
    new_title = message.caption
    if not new_title: return
    
    res = db_query("SELECT v_id, ep_num, quality, duration, post_id FROM videos WHERE poster_id=%s LIMIT 1", (message.photo.file_id,))
    if res and res[0][4]: # التأكد من وجود post_id
        v_id, ep, q, dur, post_id = res[0]
        db_query("UPDATE videos SET title=%s WHERE v_id=%s", (new_title, v_id), fetch=False)
        
        safe_title = obfuscate_visual(escape(new_title))
        new_caption = (
            f"🎬 <b>{safe_title}</b>\n\n"
            f"الحلقة: [{ep}]\n"
            f"الجودة: [{q}]\n"
            f"المدة: [{dur}]\n\n"
            f"نتمنى لكم مشاهدة ممتعة."
        )
        me = await client.get_me()
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
        
        try:
            await client.edit_message_caption(chat_id=PUBLIC_POST_CHANNEL, message_id=int(post_id), caption=new_caption, reply_markup=markup)
            logger.info(f"✅ Updated post {post_id} from source edit.")
        except Exception as e:
            logger.error(f"❌ Edit Failed: {e}")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    init_database()
    logger.info("🚀 Bot is starting...")
    app.run()
