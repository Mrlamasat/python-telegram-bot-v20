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

# تصحيح رابط قاعدة البيانات
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@khofkrjrnrqnrnta" 

app = Client("CinemaBot_AutoSave", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- إدارة قاعدة البيانات ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    res = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetchone: res = cursor.fetchone()
        elif fetchall: res = cursor.fetchall()
        if commit: conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"❌ Database Error: {e}")
    finally:
        if conn: conn.close()
    return res

def init_db():
    db_query('CREATE TABLE IF NOT EXISTS episodes (v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, quality TEXT)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS temp_upload (chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, step TEXT)', commit=True)

# --- دالة عرض الحلقة مع ميزة التسجيل التلقائي ---
async def send_episode_details(client, chat_id, v_id):
    # 1. البحث في القاعدة
    ep = db_query("SELECT poster_id, title, ep_num, duration, quality FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
    
    # 2. ميزة التسجيل التلقائي: إذا لم تكن الحلقة موجودة في القاعدة
    if not ep:
        try:
            msg = await client.get_messages(ADMIN_CHANNEL, int(v_id))
            if msg and (msg.video or msg.document):
                title = msg.caption or "بدون عنوان (تسجيل تلقائي)"
                duration_sec = msg.video.duration if msg.video else getattr(msg.document, "duration", 0)
                duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
                
                # حفظ البيانات فوراً في PostgreSQL
                db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s)", 
                         (v_id, "default", title, 0, duration, "Auto"), commit=True)
                
                ep = ("default", title, 0, duration, "Auto")
            else:
                return await client.send_message(chat_id, "❌ عذراً، هذا الرابط غير صالح أو الفيديو محذوف من المصدر.")
        except Exception as e:
            logger.error(f"Auto-save failed: {e}")
            return await client.send_message(chat_id, "❌ حدث خطأ أثناء جلب بيانات الحلقة.")

    poster_id, title, ep_num, duration, quality = ep

    try:
        # إرسال الفيديو أولاً
        await client.copy_message(chat_id, ADMIN_CHANNEL, int(v_id), protect_content=True)

        # جلب قائمة الحلقات المتسلسلة
        buttons = []
        if poster_id != "default":
            all_eps = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=%s ORDER BY ep_num ASC", (poster_id,), fetchall=True)
            row = []
            for vid, num in all_eps:
                label = f"⭐ {num}" if str(vid) == str(v_id) else f"{num}"
                row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
                if len(row) == 4: buttons.append(row); row = []
            if row: buttons.append(row)

        header = f"🎬 **{title}**\n" if title else ""
        caption = f"{header}📦 **حلقة رقم:** {ep_num}\n⏱ **المدة:** {duration}\n✨ **الجودة:** {quality}"
        
        await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

    except Exception as e:
        logger.error(f"Error sending episode: {e}")

# --- معالجة الحركات والبداية ---
@app.on_callback_query(filters.regex(r"^go_"))
async def on_navigate(client, query):
    await query.message.delete()
    await send_episode_details(client, query.from_user.id, query.data.split("_")[1])

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        await send_episode_details(client, message.chat.id, message.command[1])
    else:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت السينما.")

# --- نظام الرفع (للمحتوى الجديد) ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo & ~filters.sticker)
async def on_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step=EXCLUDED.step", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ استلمت الفيديو. أرسل البوستر الآن:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker | filters.document))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_poster": return
    p_id = message.photo.file_id if message.photo else (message.sticker.file_id if message.sticker else message.document.file_id)
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step=%s WHERE chat_id=%s", 
             (p_id, message.caption or "", "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
    await message.reply_text("🔢 أرسل رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num": return
    if not message.text.isdigit(): return
    db_query("UPDATE temp_upload SET ep_num=%s, step=%s WHERE chat_id=%s", (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
    await message.reply_text("✨ اختر الجودة:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="q_720p"), InlineKeyboardButton("1080p", callback_data="q_1080p")]]))

@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not data: return
    v_id, poster_id, title, ep_num, duration = data

    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s)", 
             (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = (f"🎬 **{title}**\n" if title else "") + f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
    
    try:
        path = await asyncio.wait_for(client.download_media(poster_id), timeout=15)
        with Image.open(path) as img:
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            bio = io.BytesIO(); bio.name="p.png"; bg.save(bio, "PNG"); bio.seek(0)
            await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=watch_link)]]))
        os.remove(path)
    except:
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=watch_link)]]))

    await query.message.edit_text("🚀 تم النشر!")

if __name__ == "__main__":
    init_db()
    app.run()
