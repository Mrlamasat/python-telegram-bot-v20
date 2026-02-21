import os
import sqlite3
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# المعرفات (قناة التخزين وقناة الاختبار)
ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@khofkrjrnrqnrnta" 
NEW_BOT_USERNAME = "Bottemo_bot" 

app = Client("CinemaBot_Final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- قاعدة البيانات ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect("cinema.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone: res = cursor.fetchone()
    if fetchall: res = cursor.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS episodes 
                (v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT, 
                 ep_num INTEGER, duration TEXT, quality TEXT)''', commit=True)
    db_query('''CREATE TABLE IF NOT EXISTS temp_upload 
                (chat_id INTEGER PRIMARY KEY, v_id TEXT, poster_id TEXT, 
                 title TEXT, ep_num INTEGER, duration TEXT, step TEXT)''', commit=True)

init_db()

# --- 1. استلام الفيديو ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo & ~filters.sticker)
async def on_video(client, message):
    if message.document and "image" in (message.document.mime_type or ""):
        return 

    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"

    db_query("INSERT OR REPLACE INTO temp_upload (chat_id, v_id, duration, step) VALUES (?, ?, ?, ?)", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ تم استلام الفيديو\n🖼 الآن أرسل (البوستر) بأي صيغة (حتى WebP):")

# --- 2. استلام البوستر (دعم شامل لجميع الصيغ) ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker | filters.document))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_poster":
        return

    try:
        # جلب المعرف بناءً على نوع الملف
        if message.photo:
            photo_id = message.photo.file_id
        elif message.sticker:
            photo_id = message.sticker.file_id
        elif message.document and "image" in (message.document.mime_type or ""):
            photo_id = message.document.file_id
        else:
            return

        title = message.caption if message.caption else ""
        
        db_query("UPDATE temp_upload SET poster_id = ?, title = ?, step = ? WHERE chat_id = ?", 
                 (photo_id, title, "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
        
        await message.reply_text("🖼 تم حفظ البوستر بنجاح\n🔢 أرسل الآن رقم الحلقة:")
    except Exception as e:
        logging.error(f"Error saving poster: {e}")
        await message.reply_text("⚠️ حدث خطأ في معالجة الصورة، حاول مجدداً.")

# --- 3. استلام رقم الحلقة ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num": return
    
    if not message.text.isdigit():
        return await message.reply_text("❌ أرسل رقماً فقط!")
    
    db_query("UPDATE temp_upload SET ep_num=?, step=? WHERE chat_id=?", 
             (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
    
    btns = InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="q_720p"), InlineKeyboardButton("1080p", callback_data="q_1080p")], [InlineKeyboardButton("4K", callback_data="q_4K")]])
    await message.reply_text("✨ اختر جودة الفيديو:", reply_markup=btns)

# --- 4. النشر النهائي (معالجة ذكية للصور والـ WebP) ---
@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not data: return

    v_id, poster_id, title, ep_num, duration = data
    db_query("INSERT OR REPLACE INTO episodes VALUES (?, ?, ?, ?, ?, ?)", (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)

    bot_username = (await client.get_me()).username
    watch_link = f"https://t.me/{bot_username}?start={v_id}"
    
    caption = ""
    if title and title.strip():
        caption += f"🎬 **{title}**\n"
    caption += f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر لمشاهدة الحلقة"
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
    
    # محاولة النشر في قناة الاختبار
    try:
        # المحاولة 1: إرسال كصورة (تنجح مع الصور العادية)
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)
    except Exception:
        try:
            # المحاولة 2: إرسال كملف (تنجح مع WebP والملصقات وتظهر كصورة في القناة)
            await client.send_document(TEST_CHANNEL, document=poster_id, caption=caption, reply_markup=markup)
        except Exception as e:
            # المحاولة 3: نص فقط في حال الفشل التام
            await client.send_message(TEST_CHANNEL, caption, reply_markup=markup)
            logging.error(f"Final publishing error: {e}")
    
    await query.message.edit_text(f"🚀 تم النشر بنجاح في قناة الاختبار: {TEST_CHANNEL}")

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        # نظام عرض الحلقة للمستخدم (سيتم جلب الفيديو من قناة التخزين)
        v_id = message.command[1]
        await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
    else:
        await message.reply_text("أهلاً بك يا محمد! البوت جاهز للاختبار.")

print("🚀 البوت يعمل الآن..")
app.run()
