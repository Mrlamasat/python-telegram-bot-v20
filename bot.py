import os
import sqlite3
import logging
import io
from PIL import Image
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# الإعدادات
logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@khofkrjrnrqnrnta" 

app = Client("CinemaBot_Final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- قاعدة البيانات ---
def db_query(query, params=(), commit=False):
    conn = sqlite3.connect("cinema.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = cursor.fetchone() if not commit else None
    if commit: conn.commit()
    conn.close()
    return res

# --- 1. استلام الفيديو ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo & ~filters.sticker)
async def on_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"

    db_query("INSERT OR REPLACE INTO temp_upload (chat_id, v_id, duration, step) VALUES (?, ?, ?, ?)", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ تم استلام الفيديو\n🖼 الآن أرسل (البوستر) بأي صيغة:")

# --- 2. استلام البوستر ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker | filters.document))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,))
    if not res or res[0] != "awaiting_poster": return

    # جلب الـ ID
    p_id = message.photo.file_id if message.photo else (message.sticker.file_id if message.sticker else message.document.file_id)
    title = message.caption if message.caption else ""
    
    db_query("UPDATE temp_upload SET poster_id = ?, title = ?, step = ? WHERE chat_id = ?", 
             (p_id, title, "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
    await message.reply_text("🖼 تم حفظ البوستر\n🔢 أرسل الآن رقم الحلقة:")

# --- 3. استلام رقم الحلقة ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,))
    if not res or res[0] != "awaiting_ep_num": return
    if not message.text.isdigit(): return await message.reply_text("❌ أرسل رقماً!")
    
    db_query("UPDATE temp_upload SET ep_num=?, step=? WHERE chat_id=?", (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
    btns = InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="q_720p"), InlineKeyboardButton("1080p", callback_data="q_1080p")]])
    await message.reply_text("✨ اختر جودة الفيديو:", reply_markup=btns)

# --- 4. النشر النهائي (مع تطبيق فكرتك في تحويل WebP) ---
@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,))
    if not data: return
    v_id, poster_id, title, ep_num, duration = data

    # حفظ البيانات وحذف المؤقت
    db_query("INSERT OR REPLACE INTO episodes VALUES (?, ?, ?, ?, ?, ?)", (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = f"🎬 **{title}**\n" if title else ""
    caption += f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر للمشاهدة"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])

    # تطبيق فكرتك (تحويل الصيغ)
    try:
        sent_status = False
        # تحميل الملف من تليجرام لمعالجته
        file_path = await client.download_media(poster_id)
        
        # تحويل WebP أو الصيغ الأخرى إلى PNG لضمان ظهورها كصورة
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            bio = io.BytesIO()
            bio.name = "poster.png"
            img.save(bio, "PNG")
            bio.seek(0)
            await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption, reply_markup=markup)
            sent_status = True
            
        # مسح الملف المؤقت بعد التحويل
        if os.path.exists(file_path): os.remove(file_path)

    except Exception as e:
        logging.error(f"Pillow Error: {e}")
        # إذا فشل التحويل، نرسلها بالطريقة العادية كخطة بديلة
        try: await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)
        except: await client.send_message(TEST_CHANNEL, caption, reply_markup=markup)

    await query.message.edit_text(f"🚀 تم النشر بنجاح في قناة الاختبار!")

app.run()
