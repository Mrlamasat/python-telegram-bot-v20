import os
import psycopg2
import logging
import io
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات التسجيل لمراقبة الأداء في Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# المتغيرات الأساسية (تُسحب من Variables في Railway)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# جلب وتصحيح رابط قاعدة البيانات
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# معرفات القنوات
ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@khofkrjrnrqnrnta" 

app = Client("CinemaBot_Final_Postgres", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- إدارة قاعدة البيانات (PostgreSQL) ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    res = None
    try:
        # الاتصال باستخدام SSL لضمان الأمان في Railway
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
        logger.error(f"❌ Database Error: {e}")
    finally:
        if conn:
            conn.close()
    return res

def init_db():
    # إنشاء جداول البيانات إذا لم تكن موجودة
    db_query('CREATE TABLE IF NOT EXISTS episodes (v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, quality TEXT)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS temp_upload (chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, step TEXT)', commit=True)
    logger.info("✅ Database tables are ready and synchronized!")

# --- دالة عرض الحلقة (مع أزرار الحلقات المتسلسلة) ---
async def send_episode_details(client, chat_id, v_id):
    ep = db_query("SELECT poster_id, title, ep_num, duration, quality FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
    if not ep:
        return await client.send_message(chat_id, "❌ عذراً، لم يتم العثور على هذه الحلقة.")

    poster_id, title, ep_num, duration, quality = ep
    try:
        # إرسال الفيديو (محمي من التوجيه)
        await client.copy_message(chat_id, ADMIN_CHANNEL, int(v_id), protect_content=True)

        # جلب كافة الحلقات المرتبطة بنفس البوستر
        all_eps = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=%s ORDER BY ep_num ASC", (poster_id,), fetchall=True)
        
        buttons = []
        row = []
        for vid, num in all_eps:
            label = f"⭐ {num}" if str(vid) == str(v_id) else f"{num}"
            row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row: buttons.append(row)

        header = f"🎬 **{title}**\n" if title and title.strip() else ""
        caption = (f"{header}📦 **حلقة رقم:** {ep_num}\n⏱ **المدة:** {duration}\n"
                   f"✨ **الجودة:** {quality}\n\n📖 **شاهد باقي الحلقات:**")
        
        await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Error in send_episode_details: {e}")

# --- معالجة التنقل والبداية ---
@app.on_callback_query(filters.regex(r"^go_"))
async def on_navigate(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await send_episode_details(client, query.from_user.id, v_id)

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        await send_episode_details(client, message.chat.id, message.command[1])
    else:
        await message.reply_text(f"أهلاً بك يا محمد! البوت يعمل الآن بنظام PostgreSQL المتطور.")

# --- مراحل رفع المحتوى (الأدمن) ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo & ~filters.sticker)
async def on_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, duration=EXCLUDED.duration, step=EXCLUDED.step", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ تم استلام الفيديو\n🖼 أرسل الآن البوستر (صورة أو ملصق):")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker | filters.document))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_poster": return

    p_id = message.photo.file_id if message.photo else (message.sticker.file_id if message.sticker else message.document.file_id)
    title = message.caption if message.caption else ""
    
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step=%s WHERE chat_id=%s", 
             (p_id, title, "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
    await message.reply_text("🔢 أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num": return
    if not message.text.isdigit(): return
    
    db_query("UPDATE temp_upload SET ep_num=%s, step=%s WHERE chat_id=%s", (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
    btns = InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="q_720p"), InlineKeyboardButton("1080p", callback_data="q_1080p")]])
    await message.reply_text("✨ اختر جودة الفيديو للنشر:", reply_markup=btns)

@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not data: return
    v_id, poster_id, title, ep_num, duration = data

    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET quality=EXCLUDED.quality", 
             (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = (f"🎬 **{title}**\n" if title else "") + f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر للمشاهدة"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])

    # معالجة البوستر (تحويل WebP إلى PNG)
    try:
        file_path = await client.download_media(poster_id)
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            bio = io.BytesIO()
            bio.name = "poster.png"
            img.save(bio, "PNG")
            bio.seek(0)
            await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption, reply_markup=markup)
        if os.path.exists(file_path): os.remove(file_path)
    except:
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)

    await query.message.edit_text("🚀 تم النشر بنجاح في القناة!")

if __name__ == "__main__":
    init_db()
    app.run()
