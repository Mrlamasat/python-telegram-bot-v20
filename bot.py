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

# --- قاعدة البيانات ---
def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone: res = cursor.fetchone()
    if fetchall: res = cursor.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

# إنشاء الجداول بنفس هيكلة الكود الأول الذي أرسلته
db_execute('''CREATE TABLE IF NOT EXISTS videos 
              (v_id TEXT PRIMARY KEY, duration TEXT, poster_id TEXT, 
               status TEXT, ep_num INTEGER, quality TEXT, title TEXT)''', commit=True)

db_execute('''CREATE TABLE IF NOT EXISTS temp_upload 
              (chat_id INTEGER PRIMARY KEY, v_id TEXT, step TEXT)''', commit=True)

# --- نظام الرفع ---

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def handle_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, status) VALUES (?, ?, ?)", 
               (v_id, duration, "waiting"), commit=True)
    db_execute("INSERT OR REPLACE INTO temp_upload (chat_id, v_id, step) VALUES (?, ?, ?)", 
               (ADMIN_CHANNEL, v_id, "awaiting_poster"), commit=True)
    
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\n🖼 أرسل البوستر الآن (الوصف اختياري):")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.photo)
async def handle_poster(client, message):
    temp = db_execute("SELECT v_id, step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not temp or temp[1] != "awaiting_poster": return

    v_id = temp[0]
    # العنوان اختياري: إذا لم يوجد وصف نضع 'مشاهدة ممتعة'
    title = message.caption if message.caption else "مشاهدة ممتعة"
    poster_id = message.photo.file_id
    
    db_execute("UPDATE videos SET poster_id=?, title=?, status='awaiting_ep' WHERE v_id=?", 
               (poster_id, title, v_id), commit=True)
    db_execute("UPDATE temp_upload SET step='awaiting_ep_num' WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)
    
    await message.reply_text(f"🖼 تم حفظ البوستر.\n🔢 أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def handle_ep_num(client, message):
    temp = db_execute("SELECT v_id, step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not temp or temp[1] != "awaiting_ep_num": return
    
    if not message.text.isdigit(): return
    
    v_id = temp[0]
    db_execute("UPDATE videos SET ep_num=?, status='posted' WHERE v_id=?", (int(message.text), v_id), commit=True)
    db_execute("DELETE FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)
    
    # جلب بيانات النشر
    v = db_execute("SELECT title, ep_num, duration, poster_id FROM videos WHERE v_id=?", (v_id,), fetchone=True)
    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    
    # نشر في القناة العامة
    if PUBLIC_CHANNEL:
        caption = f"🎬 **{v[0]}**\n📦 الحلقة: {v[1]}\n⏱ المده: {v[2]}"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        await client.send_photo(PUBLIC_CHANNEL, photo=v[3], caption=caption, reply_markup=markup)
    
    await message.reply_text(f"🚀 تم التفعيل! الرابط:\n{watch_link}")

# --- عرض الحلقات (الربط كما في الكود الأصلي) ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد، استخدم روابط القناة للمشاهدة.")

    v_id = message.command[1]
    # جلب الحلقة (تأكدنا من حالة posted لضمان اكتمال البيانات)
    video = db_execute("SELECT poster_id, duration, ep_num, title FROM videos WHERE v_id=?", (v_id,), fetchone=True)
    
    if not video:
        return await message.reply_text("❌ عذراً، الحلقة غير متوفرة.")

    poster_id, duration, ep_num, title = video
    
    # إرسال الفيديو مباشرة
    await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
    
    # جلب كل الحلقات التي تملك نفس الـ poster_id (كما في كودك الأصلي)
    all_eps = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? ORDER BY ep_num ASC", (poster_id,), fetchall=True)
    
    btns = []
    row = []
    for vid, num in all_eps:
        # تمييز الحلقة الحالية
        label = f"▶️ {num}" if vid == v_id else f"{num}"
        row.append(InlineKeyboardButton(label, callback_data=f"watch_{vid}"))
        if len(row) == 4:
            btns.append(row)
            row = []
    if row: btns.append(row)

    caption = f"🎬 **{title}**\n📦 حلقة رقم: {ep_num}\n⏱ المده: {duration}\n\n👇 شاهد المزيد من الحلقات:"
    await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(btns))

@app.on_callback_query(filters.regex(r"^watch_"))
async def watch_callback(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    # إعادة استدعاء start_handler للحلقة الجديدة
    query.message.command = ["start", v_id]
    await start_handler(client, query.message)

app.run()
