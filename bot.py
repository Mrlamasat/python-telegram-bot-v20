import os
import psycopg2
import logging
import io
import asyncio
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# 1. إعدادات التسجيل لمتابعة العمليات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. المتغيرات (Railway Variables)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# يوزر البوت الجديد وقنوات التواصل
NEW_BOT_USERNAME = "Bottemo_bot" 
ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@khofkrjrnrqnrnta" 

app = Client("CinemaBot_Final_Safe", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- 3. إدارة قاعدة البيانات (حل مشكلة Socket نهائياً) ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    res = None
    # جلب الرابط من متغيرات البيئة
    url = os.environ.get("DATABASE_URL")
    
    if not url:
        logger.error("❌ DATABASE_URL is missing!")
        return None

    try:
        # تصحيح البروتوكول ليتوافق مع psycopg2
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        
        # الاتصال المباشر مع فرض SSL لإلغاء محاولة الاتصال المحلي
        conn = psycopg2.connect(url, sslmode='require', connect_timeout=10)
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetchone: res = cursor.fetchone()
        elif fetchall: res = cursor.fetchall()
        if commit: conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
    finally:
        if conn: conn.close()
    return res

def init_db():
    db_query('CREATE TABLE IF NOT EXISTS episodes (v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, quality TEXT)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS temp_upload (chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, step TEXT)', commit=True)
    logger.info("✅ Database Synchronized!")

# --- 4. منطق العرض والتسجيل التلقائي (إخفاء النصوص الزائدة) ---
async def send_episode_details(client, chat_id, v_id):
    ep = db_query("SELECT poster_id, title, ep_num, duration, quality FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
    
    # التسجيل التلقائي الصامت للروابط القديمة
    if not ep:
        try:
            msg = await client.get_messages(ADMIN_CHANNEL, int(v_id))
            if msg and (msg.video or msg.document):
                dur_sec = msg.video.duration if msg.video else getattr(msg.document, "duration", 0)
                duration = f"{dur_sec // 60}:{dur_sec % 60:02d}"
                db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s)", 
                         (v_id, "default", "Auto", 0, duration, "Auto"), commit=True)
                ep = ("default", "Auto", 0, duration, "Auto")
        except: pass

    if not ep: return await client.send_message(chat_id, "❌ الحلقة غير موجودة.")

    poster_id, title, ep_num, duration, quality = ep
    try:
        await client.copy_message(chat_id, ADMIN_CHANNEL, int(v_id), protect_content=True)
        
        # إذا كانت حلقة تلقائية (رقمها 0)، ننهي الدالة هنا (لا نرسل نصاً)
        if ep_num == 0: return 

        # الحلقات المرفوعة يدوياً: إرسال الأزرار والتفاصيل
        all_eps = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=%s ORDER BY ep_num ASC", (poster_id,), fetchall=True)
        buttons = []
        row = []
        for vid, num in all_eps:
            label = f"⭐ {num}" if str(vid) == str(v_id) else f"{num}"
            row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
            if len(row) == 4: buttons.append(row); row = []
        if row: buttons.append(row)

        caption = f"🎬 **{title}**\n🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
        await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Error: {e}")

# --- 5. نظام الرفع الاحترافي (منع التوقف عند البوستر) ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo & ~filters.sticker)
async def on_video(client, message):
    v_id = str(message.id)
    dur_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{dur_sec // 60}:{dur_sec % 60:02d}"
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step=EXCLUDED.step", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ تم استلام الفيديو.\n🖼 أرسل الآن البوستر (صورة أو ملصق):")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker | filters.document))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_poster": return
    
    p_id = message.photo.file_id if message.photo else (message.sticker.file_id if message.sticker else message.document.file_id)
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step=%s WHERE chat_id=%s", 
             (p_id, message.caption or "", "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
    await message.reply_text("🔢 استلمت البوستر.\nأرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num": return
    if not message.text.isdigit(): return
    
    db_query("UPDATE temp_upload SET ep_num=%s, step=%s WHERE chat_id=%s", (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
    await message.reply_text("✨ اختر الجودة:", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("720p", callback_data="q_720p"),
        InlineKeyboardButton("1080p", callback_data="q_1080p")
    ]]))

@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not data: return
    v_id, poster_id, title, ep_num, duration = data

    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality", 
             (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{NEW_BOT_USERNAME}?start={v_id}"
    caption = (f"🎬 **{title}**\n" if title else "") + f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
    
    await query.message.edit_text("⏳ جاري النشر...")
    
    # معالجة البوستر بأمان (دعم WebP والصور الشفافة)
    file_path = None
    try:
        file_path = await asyncio.wait_for(client.download_media(poster_id), timeout=25)
        with Image.open(file_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                final_img = bg
            else:
                final_img = img.convert("RGB")
            
            bio = io.BytesIO(); bio.name="p.png"
            final_img.save(bio, "PNG"); bio.seek(0)
            await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=watch_link)]]))
        if os.path.exists(file_path): os.remove(file_path)
    except:
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=watch_link)]]))

    await query.message.edit_text("🚀 تم النشر!")

# --- 6. التحويل والبداية ---
@app.on_callback_query(filters.regex(r"^go_"))
async def on_navigate(client, query):
    await query.message.delete()
    await send_episode_details(client, query.from_user.id, query.data.split("_")[1])

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        # إذا كان هذا هو البوت القديم (التحويل)
        if client.me.username != NEW_BOT_USERNAME:
            new_link = f"https://t.me/{NEW_BOT_USERNAME}?start={v_id}"
            return await message.reply_text("⚠️ **انتقلنا لبوت جديد!**\nاضغط للبدء:", 
                                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=new_link)]]))
        # إذا كان البوت الجديد
        await send_episode_details(client, message.chat.id, v_id)
    else:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}!")

if __name__ == "__main__":
    init_db()
    app.run()
