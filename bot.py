import os
import psycopg2
import logging
import io
import asyncio
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# المتغيرات الأساسية
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_CHANNEL = -1003547072209 
# قناة النشر (يمكنك تغييرها لقناتك العامة)
TEST_CHANNEL = "@khofkrjrnrqnrnta" 

app = Client("CinemaBot_Final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- إدارة قاعدة البيانات (PostgreSQL) ---
def db_query(query, params=(), fetchone=False, commit=False):
    conn = None
    res = None
    try:
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url, sslmode='require')
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetchone: res = cursor.fetchone()
        if commit: conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"❌ DB Error: {e}")
    finally:
        if conn: conn.close()
    return res

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS episodes 
                (v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT, 
                 ep_num INTEGER, duration TEXT, quality TEXT)''', commit=True)
    db_query('''CREATE TABLE IF NOT EXISTS temp_upload 
                (chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, 
                 title TEXT, ep_num INTEGER, duration TEXT, step TEXT)''', commit=True)

# --- نظام التشغيل وجلب الحلقات ---
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # البحث في القاعدة
        ep = db_query("SELECT poster_id, title FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
        
        if ep:
            if ep[0] not in ["auto", None]:
                await client.send_photo(message.chat.id, photo=ep[0], caption=f"🎬 **{ep[1]}**")
            await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
        else:
            # التسجيل التلقائي إذا لم تكن موجودة
            try:
                msg = await client.get_messages(ADMIN_CHANNEL, int(v_id))
                if msg:
                    await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
                    db_query("INSERT INTO episodes (v_id, poster_id, title) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
                             (v_id, "auto", "حلقة مسجلة تلقائياً"), commit=True)
            except Exception:
                await message.reply_text("❌ عذراً، هذه الحلقة غير متوفرة.")
    else:
        await message.reply_text(f"أهلاً بك يا محمد! البوت يعمل بنجاح.")

# --- نظام الرفع المتسلسل (Admin) ---

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo)
async def on_video(client, message):
    if message.document and "image" in (message.document.mime_type or ""): return
    
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"

    db_query("""INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, %s) 
                ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, duration=EXCLUDED.duration, step='awaiting_poster'""", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ تم استلام الفيديو\n🖼 الآن أرسل (البوستر) كصورة أو ملصق:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_poster": return

    p_id = message.photo.file_id if message.photo else message.sticker.file_id
    title = message.caption if message.caption else "بدون عنوان"
    
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep_num' WHERE chat_id=%s", 
             (p_id, title, ADMIN_CHANNEL), commit=True)
    await message.reply_text("🖼 تم حفظ البوستر\n🔢 أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_ep_num(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num": return
    if not message.text.isdigit(): return await message.reply_text("❌ أرسل رقماً!")
    
    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s", 
             (int(message.text), ADMIN_CHANNEL), commit=True)
    
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("720p", callback_data="q_720p"),
        InlineKeyboardButton("1080p", callback_data="q_1080p")
    ]])
    await message.reply_text("✨ اختر جودة الفيديو لنشرها:", reply_markup=btns)

# --- النشر النهائي ومعالجة الصورة ---
@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality_finish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not data: return
    
    v_id, poster_id, title, ep_num, duration = data

    # حفظ في قاعدة البيانات النهائية
    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id", 
             (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)

    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    caption = f"🎬 **{title}**\n🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر للمشاهدة"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])

    await query.message.edit_text("⏳ جاري معالجة الصورة ونشرها في القناة...")

    try:
        # تحميل وتحويل الصورة لضمان ظهورها بشكل صحيح في التيليجرام
        file_path = await client.download_media(poster_id)
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            bio = io.BytesIO()
            bio.name = "poster.png"
            img.save(bio, "PNG")
            bio.seek(0)
            await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption, reply_markup=markup)
        
        if os.path.exists(file_path): os.remove(file_path)
        await query.message.edit_text("🚀 تم النشر بنجاح!")
    except Exception as e:
        logger.error(f"Error: {e}")
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)
        await query.message.edit_text("🚀 تم النشر (بدون تحويل الصورة)!")

if __name__ == "__main__":
    init_db()
    logger.info("Bot is running...")
    app.run()
