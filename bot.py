import os
import psycopg2
import logging
import io
import asyncio
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# المتغيرات
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@khofkrjrnrqnrnta" 
NEW_BOT_USERNAME = "Bottemo_bot"

app = Client("CinemaBot_Fixed_Upload", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- إدارة قاعدة البيانات ---
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
    db_query('CREATE TABLE IF NOT EXISTS episodes (v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, quality TEXT)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS temp_upload (chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, title TEXT, ep_num INTEGER, duration TEXT, step TEXT)', commit=True)

# --- نظام الرفع الجديد (خطوة بخطوة) ---

# 1. استقبال الفيديو
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo)
async def on_video(client, message):
    v_id = str(message.id)
    dur_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{dur_sec // 60}:{dur_sec % 60:02d}"
    
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'wait_poster') ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='wait_poster'", (ADMIN_CHANNEL, v_id, duration), commit=True)
    await message.reply_text(f"✅ تم استلام الفيديو.\n🖼 الآن أرسل **البوستر** (صورة أو ملصق):")

# 2. استقبال البوستر (صورة أو ملصق)
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker))
async def on_poster(client, message):
    res = db_query("SELECT v_id FROM temp_upload WHERE chat_id=%s AND step='wait_poster'", (ADMIN_CHANNEL,), fetchone=True)
    if not res: return
    
    p_id = message.photo.file_id if message.photo else message.sticker.file_id
    title = message.caption if message.caption else "عنوان تلقائي"
    
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='wait_ep_num' WHERE chat_id=%s", (p_id, title, ADMIN_CHANNEL), commit=True)
    await message.reply_text("🔢 ممتاز! الآن أرسل **رقم الحلقة** (أرقام فقط):")

# 3. استقبال رقم الحلقة
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_ep_num(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != 'wait_ep_num': return
    
    if not message.text.isdigit():
        return await message.reply_text("❌ يرجى إرسال أرقام فقط لرقم الحلقة.")
    
    db_query("UPDATE temp_upload SET ep_num=%s, step='wait_quality' WHERE chat_id=%s", (int(message.text), ADMIN_CHANNEL), commit=True)
    
    # إرسال أزرار اختيار الجودة
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("720p", callback_data="q_720p"),
        InlineKeyboardButton("1080p", callback_data="q_1080p")
    ]])
    await message.reply_text("✨ أخيـراً، اختر **الجودة** ليتم النشر:", reply_markup=buttons)

# 4. اختيار الجودة والنشر النهائي
@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality_selected(client, query):
    quality = query.data.split("_")[1]
    
    # جلب كل البيانات من الجدول المؤقت
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not data: return
    
    v_id, p_id, title, ep_num, duration = data
    
    # حفظ في الجدول النهائي
    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality", (v_id, p_id, title, ep_num, duration, quality), commit=True)
    
    # تنظيف المؤقت
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)
    
    # إرسال الخبر للقناة العامة (الاختبار)
    link = f"https://t.me/{NEW_BOT_USERNAME}?start={v_id}"
    await client.send_photo(TEST_CHANNEL, photo=p_id, caption=f"🎬 **{title}**\n🔢 الحلقة: {ep_num}\n✨ الجودة: {quality}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=link)]]))
    
    await query.message.edit_text("🚀 **تم النشر بنجاح في القناة وبالقاعدة!**")

# --- نظام التشغيل التلقائي (للحلقات القديمة) ---
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        ep = db_query("SELECT poster_id, title, ep_num, duration, quality FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
        
        if ep:
            # إذا كانت مسجلة بالكامل
            if ep[0] != "auto":
                await client.send_photo(message.chat.id, photo=ep[0], caption=f"🎬 **{ep[1]}**\n🔢 الحلقة: {ep[2]}\n⏱ المدة: {ep[3]}\n✨ الجودة: {ep[4]}")
            await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
        else:
            # تسجيل تلقائي للحلقات القديمة
            try:
                await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
                db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s)", (v_id, "auto", "حلقة قديمة", 0, "0:00", "Auto"), commit=True)
            except: pass
    else:
        await message.reply_text("أهلاً بك يا محمد!")

if __name__ == "__main__":
    init_db()
    app.run()
