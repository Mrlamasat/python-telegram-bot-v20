import os
import logging
import io
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2

# ----------------- إعدادات البوت -----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

ADMIN_CHANNEL = -1003547072209
TEST_CHANNEL = "@khofkrjrnrqnrnta"

app = Client("CinemaBot_Final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ----------------- إدارة قاعدة البيانات -----------------
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    res = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetchone:
            res = cursor.fetchone()
        elif fetchall:
            res = cursor.fetchall()
        if commit:
            conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"Database Error: {e}")
    finally:
        if conn:
            conn.close()
    return res

def init_db():
    db_query('''
    CREATE TABLE IF NOT EXISTS temp_upload (
        chat_id BIGINT PRIMARY KEY,
        v_id TEXT,
        poster_id TEXT,
        title TEXT,
        ep_num INTEGER,
        duration TEXT,
        step TEXT
    )
    ''', commit=True)

    db_query('''
    CREATE TABLE IF NOT EXISTS episodes (
        v_id TEXT PRIMARY KEY,
        poster_id TEXT,
        title TEXT,
        ep_num INTEGER,
        duration TEXT,
        quality TEXT
    )
    ''', commit=True)

    logger.info("✅ Database initialized")

# ----------------- رفع الفيديو -----------------
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo & ~filters.sticker)
async def on_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"

    db_query('''
        INSERT INTO temp_upload (chat_id, v_id, duration, step)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (chat_id) DO UPDATE
        SET v_id=EXCLUDED.v_id, duration=EXCLUDED.duration, step=EXCLUDED.step
    ''', (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)

    await message.reply_text("✅ تم استلام الفيديو\n🖼 أرسل البوستر الآن:")

# ----------------- رفع البوستر -----------------
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker | filters.document))
async def on_poster(client, message):
    res = db_query("SELECT chat_id FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res:
        return await message.reply_text("❌ لم يتم العثور على فيديو سابق. أرسل الفيديو أولاً.")

    poster_id = message.photo.file_id if message.photo else (message.sticker.file_id if message.sticker else message.document.file_id)
    title = message.caption or ""

    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step=%s WHERE chat_id=%s",
             (poster_id, title, "awaiting_ep_num", ADMIN_CHANNEL), commit=True)

    await message.reply_text("🖼 تم حفظ البوستر بنجاح!\n🔢 أرسل الآن رقم الحلقة:")

# ----------------- استلام رقم الحلقة -----------------
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num":
        return
    if not message.text.isdigit():
        return await message.reply_text("❌ أرسل رقماً صحيحاً!")

    db_query("UPDATE temp_upload SET ep_num=%s, step=%s WHERE chat_id=%s",
             (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)

    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("720p", callback_data="q_720p"),
         InlineKeyboardButton("1080p", callback_data="q_1080p")]
    ])
    await message.reply_text("✨ اختر جودة الفيديو:", reply_markup=btns)

# ----------------- اختيار الجودة والنشر -----------------
@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not data:
        return await query.answer("❌ لم يتم العثور على بيانات الفيديو.", show_alert=True)

    v_id, poster_id, title, ep_num, duration = data

    # حفظ الحلقة النهائية
    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s,%s,%s,%s,%s,%s)",
             (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = (f"🎬 **{title}**\n" if title else "") + f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط للمشاهدة"

    # محاولة تحويل البوستر إلى PNG إذا كان WebP أو Sticker
    try:
        file = await client.download_media(poster_id, in_memory=True)
        from PIL import Image
        with Image.open(file) as img:
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            bio = io.BytesIO()
            bio.name = "poster.png"
            bg.save(bio, "PNG")
            bio.seek(0)
            await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption,
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=watch_link)]]))
    except:
        # fallback: إرسال الصورة الأصلية
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption,
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=watch_link)]]))

    await query.message.edit_text("🚀 تم النشر بنجاح!")

# ----------------- تشغيل البوت -----------------
if __name__ == "__main__":
    init_db()
    logger.info("🚀 البوت يعمل الآن!")
    app.run()
