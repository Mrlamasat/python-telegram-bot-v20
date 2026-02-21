import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHANNEL = -1003547072209 
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")

app = Client("CinemaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- التعامل مع قاعدة البيانات القديمة ---
def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    # نستخدم نفس اسم ملفك القديم
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone: res = cursor.fetchone()
    if fetchall: res = cursor.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

def init_db():
    # التأكد من وجود الأعمدة المطلوبة في جدولك القديم أو إنشاؤه إذا لم يوجد
    db_execute('''CREATE TABLE IF NOT EXISTS videos 
                  (v_id TEXT PRIMARY KEY, duration TEXT, poster_id TEXT, 
                   status TEXT, ep_num INTEGER, quality TEXT, title TEXT)''', commit=True)
    # جدول مؤقت للرفع الجديد
    db_execute('''CREATE TABLE IF NOT EXISTS temp_upload 
                  (chat_id INTEGER PRIMARY KEY, v_id TEXT, step TEXT)''', commit=True)

init_db()

# --- سير العمل (الرفع الجديد) ---

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def handle_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    
    # حفظ الفيديو في الجدول الرئيسي بحالة 'waiting'
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (v_id, duration, "waiting"), commit=True)
    db_execute("INSERT OR REPLACE INTO temp_upload (chat_id, v_id, step) VALUES (?, ?, ?)", 
               (ADMIN_CHANNEL, v_id, "awaiting_poster"), commit=True)
    
    await message.reply_text("✅ تم استلام الفيديو.\n🖼 أرسل البوستر الآن مع (العنوان في الوصف):")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.photo)
async def handle_poster(client, message):
    temp = db_execute("SELECT v_id, step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not temp or temp[1] != "awaiting_poster": return

    v_id = temp[0]
    title = message.caption if message.caption else "عنوان غير مسمى"
    db_execute("UPDATE videos SET poster_id=?, title=?, status='awaiting_ep' WHERE v_id=?", 
               (message.photo.file_id, title, v_id), commit=True)
    db_execute("UPDATE temp_upload SET step='awaiting_ep_num' WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)
    
    await message.reply_text(f"🖼 تم حفظ البوستر لـ **{title}**\n🔢 أرسل رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def handle_ep_num(client, message):
    temp = db_execute("SELECT v_id, step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not temp or temp[1] != "awaiting_ep_num": return
    
    if not message.text.isdigit(): return await message.reply_text("أرسل رقماً فقط!")
    
    db_execute("UPDATE videos SET ep_num=?, status='awaiting_quality' WHERE v_id=?", (int(message.text), temp[0]), commit=True)
    db_execute("UPDATE temp_upload SET step='awaiting_quality' WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)
    
    btns = InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="set_720p"), 
                                  InlineKeyboardButton("1080p", callback_data="set_1080p")]])
    await message.reply_text("✨ اختر الجودة لنشر الحلقة:", reply_markup=btns)

@app.on_callback_query(filters.regex(r"^set_"))
async def finalize_post(client, query):
    quality = query.data.split("_")[1]
    temp = db_execute("SELECT v_id FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not temp: return

    v_id = temp[0]
    db_execute("UPDATE videos SET quality=?, status='posted' WHERE v_id=?", (quality, v_id), commit=True)
    db_execute("DELETE FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)
    
    # جلب البيانات للنشر
    info = db_execute("SELECT title, ep_num, duration, poster_id FROM videos WHERE v_id=?", (v_id,), fetchone=True)
    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    
    caption = f"🎬 **{info[0]}**\n🔢 حلقة رقم: {info[1]}\n⏱ المدة: {info[2]}\n✨ الجودة: {quality}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=watch_link)]])
    
    if PUBLIC_CHANNEL:
        await client.send_photo(PUBLIC_CHANNEL, photo=info[3], caption=caption, reply_markup=markup)
    await query.message.edit_text("🚀 تم النشر بنجاح وتحديث القاعدة!")

# --- عرض الحلقات (القديمة والجديدة) ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد في بوت المشاهدة.")

    v_id = message.command[1]
    # البحث في القاعدة القديمة/الجديدة
    video = db_execute("SELECT poster_id, title, ep_num, duration, quality FROM videos WHERE v_id=? AND status='posted'", 
                       (v_id,), fetchone=True)
    
    if not video:
        return await message.reply_text("❌ هذه الحلقة غير متوفرة حالياً.")

    poster_id, title, ep_num, duration, quality = video
    
    # إرسال الفيديو من القناة
    await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
    
    # جلب قائمة "شاهد المزيد" بنفس البوستر
    all_eps = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? AND status='posted' ORDER BY ep_num ASC", 
                         (poster_id,), fetchall=True)
    
    btns = []
    row = []
    for vid, num in all_eps:
        label = f"▶️ {num}" if vid == v_id else f"{num}"
        row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
        if len(row) == 4: btns.append(row); row = []
    if row: btns.append(row)

    caption = f"🎬 **{title}**\n📦 حلقة رقم: {ep_num}\n⏱ المده: {duration}\n✨ الجودة: {quality}\n\nشاهد المزيد من الحلقات:"
    await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(btns))

@app.on_callback_query(filters.regex(r"^go_"))
async def navigate_ep(client, query):
    v_id = query.data.split("_")[1]
    # تحديث الرسالة لعرض الحلقة المختارة
    query.message.command = ["start", v_id]
    await query.message.delete()
    await start_handler(client, query.message)

app.run()
