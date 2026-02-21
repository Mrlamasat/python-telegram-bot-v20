import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHANNEL = -1003547072209 
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("CinemaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- نظام قاعدة البيانات الذكي ---
def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    try:
        conn = sqlite3.connect("bot_data.db")
        cursor = conn.cursor()
        cursor.execute(query, params)
        res = None
        if fetchone: res = cursor.fetchone()
        if fetchall: res = cursor.fetchall()
        if commit: conn.commit()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"Database Error: {e}")
        return None

def setup_database():
    # 1. إنشاء جدول الفيديوهات إذا لم يوجد
    db_execute('''CREATE TABLE IF NOT EXISTS videos 
                  (v_id TEXT PRIMARY KEY, duration TEXT, poster_id TEXT, 
                   status TEXT, ep_num INTEGER, quality TEXT, title TEXT)''', commit=True)
    
    # 2. فحص وإضافة الأعمدة الناقصة (للتوافق مع الملف القديم)
    cols = db_execute("PRAGMA table_info(videos)", fetchall=True)
    col_names = [col[1] for col in cols]
    
    for target_col in ['title', 'status', 'quality', 'ep_num']:
        if target_col not in col_names:
            try:
                db_execute(f"ALTER TABLE videos ADD COLUMN {target_col} TEXT", commit=True)
                logging.info(f"Column {target_col} added successfully.")
            except: pass

    # 3. جدول الحالات المؤقتة
    db_execute('''CREATE TABLE IF NOT EXISTS temp_upload 
                  (chat_id INTEGER PRIMARY KEY, v_id TEXT, step TEXT)''', commit=True)

setup_database()

# --- سير العمل (الرفع) ---

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def handle_video(client, message):
    v_id = str(message.id)
    # جلب المدة
    duration_sec = 0
    if message.video: duration_sec = message.video.duration
    elif message.document: duration_sec = getattr(message.document, "duration", 0)
    
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    
    # تحديث أو إضافة الفيديو
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (v_id, duration, "waiting"), commit=True)
    db_execute("INSERT OR REPLACE INTO temp_upload (chat_id, v_id, step) VALUES (?, ?, ?)", 
               (ADMIN_CHANNEL, v_id, "awaiting_poster"), commit=True)
    
    await message.reply_text("✅ **تم رصد الفيديو!**\n🖼 أرسل الآن صورة (البوستر) واكتب **العنوان** في وصف الصورة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.photo)
async def handle_poster(client, message):
    temp = db_execute("SELECT v_id, step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not temp or temp[1] != "awaiting_poster": return

    v_id = temp[0]
    title = message.caption if message.caption else "عنوان غير مسمى"
    
    db_execute("UPDATE videos SET poster_id=?, title=?, status='awaiting_ep' WHERE v_id=?", 
               (message.photo.file_id, title, v_id), commit=True)
    db_execute("UPDATE temp_upload SET step='awaiting_ep_num' WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)
    
    await message.reply_text(f"🖼 تم ربط البوستر بـ **{title}**\n🔢 أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def handle_text(client, message):
    temp = db_execute("SELECT v_id, step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not temp: return
    
    if temp[1] == "awaiting_ep_num" and message.text.isdigit():
        v_id = temp[0]
        db_execute("UPDATE videos SET ep_num=?, status='awaiting_quality' WHERE v_id=?", (int(message.text), v_id), commit=True)
        db_execute("UPDATE temp_upload SET step='awaiting_quality' WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)
        
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="set_720p"), 
                                      InlineKeyboardButton("1080p", callback_data="set_1080p")]])
        await message.reply_text("✨ اختر الجودة للنشر:", reply_markup=btns)

@app.on_callback_query(filters.regex(r"^set_"))
async def handle_quality(client, query):
    quality = query.data.split("_")[1]
    temp = db_execute("SELECT v_id FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not temp: return

    v_id = temp[0]
    db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), commit=True)
    db_execute("DELETE FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)
    
    video_data = db_execute("SELECT title, ep_num, duration, poster_id FROM videos WHERE v_id=?", (v_id,), fetchone=True)
    
    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = f"🎬 **{video_data[0]}**\n🔢 الحلقة: {video_data[1]}\n⏱ المده: {video_data[2]}\n✨ الجودة: {quality}"
    
    if PUBLIC_CHANNEL:
        await client.send_photo(PUBLIC_CHANNEL, photo=video_data[3], caption=caption, 
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]]))
    
    await query.message.edit_text(f"🚀 تم النشر بنجاح!\nالرابط: {watch_link}")

# --- عرض الحلقة للمستخدم ---

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد في بوت المشاهدة.")

    v_id = message.command[1]
    video = db_execute("SELECT poster_id, title, ep_num, duration, quality FROM videos WHERE v_id=? AND status='posted'", (v_id,), fetchone=True)
    
    if not video:
        return await message.reply_text("❌ لم يتم العثور على بيانات لهذه الحلقة.")

    poster_id, title, ep_num, duration, quality = video
    
    # 1. إرسال الفيديو
    await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
    
    # 2. جلب أزرار باقي الحلقات
    all_eps = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", (poster_id,), fetchall=True)
    
    btns = []
    row = []
    for vid, num in all_eps:
        label = f"• {num} •" if vid == v_id else f"{num}"
        row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
        if len(row) == 4: btns.append(row); row = []
    if row: btns.append(row)

    await message.reply_text(f"🎬 **{title}**\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\nشاهد المزيد من الحلقات:", 
                             reply_markup=InlineKeyboardMarkup(btns))

@app.on_callback_query(filters.regex(r"^go_"))
async def go_callback(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    query.message.command = ["start", v_id]
    await start_cmd(client, query.message)

app.run()
