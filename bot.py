import os
import psycopg2
import logging
import io
import asyncio
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# 1. إعدادات التسجيل لمراقبة Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. جلب المتغيرات الأساسية
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@khofkrjrnrqnrnta" 
NEW_BOT_USERNAME = "Bottemo_bot"

app = Client("CinemaBot_Final_Fixed", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- 3. إدارة قاعدة البيانات (مع مصحح الروابط التلقائي) ---
def db_query(query, params=(), fetchone=False, commit=False):
    conn = None
    res = None
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL missing!")
        return None
    try:
        # تصحيح الرابط ليتوافق مع مكتبة psycopg2 (بايثون)
        # يحول Postgresql:// أو postgres:// إلى postgresql://
        final_url = DATABASE_URL.replace("Postgresql://", "postgresql://", 1)
        if final_url.startswith("postgres://"):
            final_url = final_url.replace("postgres://", "postgresql://", 1)
            
        conn = psycopg2.connect(final_url, sslmode='require', connect_timeout=10)
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetchone: res = cursor.fetchone()
        if commit: conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"❌ DB Connection Error: {e}")
    finally:
        if conn: conn.close()
    return res

def init_db():
    db_query('CREATE TABLE IF NOT EXISTS episodes (v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, quality TEXT)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS temp_upload (chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, step TEXT)', commit=True)
    logger.info("✅ Database Synchronized!")

# --- 4. معالج رفع الفيديو ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo)
async def on_video(client, message):
    v_id = str(message.id)
    dur_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{dur_sec // 60}:{dur_sec % 60:02d}"

    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step=EXCLUDED.step", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ تم استلام الفيديو\n🖼 الآن أرسل (البوستر) كصورة أو ملصق:")

# --- 5. معالج رفع البوستر (استخدام Pillow للنشر المضمون) ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_poster": return

    p_id = message.photo.file_id if message.photo else message.sticker.file_id
    title = message.caption if message.caption else ""
    
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step=%s WHERE chat_id=%s", 
             (p_id, title, "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
    await message.reply_text("🖼 تم حفظ البوستر\n🔢 أرسل الآن رقم الحلقة:")

# --- 6. معالج رقم الحلقة والجودة ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num": return
    if not message.text.isdigit(): return await message.reply_text("❌ أرسل رقماً!")
    
    db_query("UPDATE temp_upload SET ep_num=%s, step=%s WHERE chat_id=%s", (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
    btns = InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="q_720p"), InlineKeyboardButton("1080p", callback_data="q_1080p")]])
    await message.reply_text("✨ اختر جودة الفيديو لنشره:", reply_markup=btns)

# --- 7. النشر النهائي في قناة الاختبار ---
@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not data: return
    v_id, poster_id, title, ep_num, duration = data

    db_query("INSERT INTO episodes VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality", (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = (f"🎬 **{title}**\n" if title else "") + f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])

    await query.message.edit_text("⏳ جاري معالجة الصورة والنشر...")

    try:
        file_path = await client.download_media(poster_id)
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            bio = io.BytesIO(); bio.name = "poster.png"
            img.save(bio, "PNG"); bio.seek(0)
            await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption, reply_markup=markup)
        if os.path.exists(file_path): os.remove(file_path)
    except:
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)

    await query.message.edit_text(f"🚀 تم النشر بنجاح!")

# --- 8. معالجة Start والتسجيل التلقائي ---
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        ep = db_query("SELECT poster_id, title FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
        
        # إذا لم تكن موجودة (تسجيل تلقائي)
        if not ep:
            try:
                # التحقق من وجودها في القناة
                msg = await client.get_messages(ADMIN_CHANNEL, int(v_id))
                if msg:
                    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (v_id, "auto", "حلقة أرشيفية", 0, "00:00", "Auto"), commit=True)
            except: pass
            
        await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
    else:
        await message.reply_text("أهلاً بك يا محمد! البوت متصل وجاهز.")

if __name__ == "__main__":
    init_db()
    app.run()
