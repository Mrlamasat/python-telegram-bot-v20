import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# الإعدادات والتسجيل
logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHANNEL = -1003547072209  # وضعته لك هنا مباشرة للتأكد
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "") 
REQ_CHANNEL = os.environ.get("REQ_CHANNEL", "")

app = Client("CinemaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

# --- استقبال الفيديو ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    # نتحقق من وجود فيديو أو مستند فيديو
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"

    db_query("INSERT OR REPLACE INTO temp_upload (chat_id, v_id, duration, step) VALUES (?, ?, ?, ?)", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    
    await message.reply_text("✅ **تم استلام الفيديو**\n🖼 الآن أرسل (البوستر) كصورة في القناة:")

# --- استقبال البوستر ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.photo)
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not state or state[0] != "awaiting_poster": return

    title = message.caption if message.caption else "عنوان غير محدد"
    db_query("UPDATE temp_upload SET poster_id=?, title=?, step=? WHERE chat_id=?", 
             (message.photo.file_id, title, "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
    
    await message.reply_text(f"🖼 تم حفظ البوستر: **{title}**\n🔢 أرسل الآن **رقم الحلقة**:")

# --- استقبال رقم الحلقة ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not state: return
    
    if state[0] == "awaiting_ep_num":
        if not message.text.isdigit():
            return await message.reply_text("❌ أرسل رقماً فقط!")
        
        db_query("UPDATE temp_upload SET ep_num=?, step=? WHERE chat_id=?", 
                 (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
        
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("720p", callback_data="q_720p"), InlineKeyboardButton("1080p", callback_data="q_1080p")],
            [InlineKeyboardButton("4K", callback_data="q_4K")]
        ])
        await message.reply_text("✨ اختر جودة الفيديو:", reply_markup=btns)

# --- معالجة الجودة والنشر النهائي ---
@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    
    if not data: return

    v_id, poster_id, title, ep_num, duration = data
    db_query("INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?)", (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = f"🎬 **{title}**\n🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=watch_link)]])
    
    if PUBLIC_CHANNEL:
        await client.send_photo(PUBLIC_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)
    
    await query.message.edit_text("🚀 تم نشر الحلقة بنجاح في القناة العامة!")

# --- عرض الحلقة للمستخدم ---
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد، ابحث عن الحلقات في القناة.")

    v_id = message.command[1]
    ep = db_query("SELECT poster_id, title, ep_num, duration, quality FROM episodes WHERE v_id=?", (v_id,), fetchone=True)
    
    if ep:
        poster_id, title, ep_num, duration, quality = ep
        # إرسال الفيديو من القناة الخاصة
        await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
        
        # جلب قائمة الحلقات
        all_eps = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=? ORDER BY ep_num ASC", (poster_id,), fetchall=True)
        buttons = []
        row = []
        for vid, num in all_eps:
            row.append(InlineKeyboardButton(f"[{num}]" if vid == v_id else f"{num}", callback_data=f"go_{vid}"))
            if len(row) == 4: buttons.append(row); row = []
        if row: buttons.append(row)

        caption = f"🎬 {title}\n📦 حلقة رقم: {ep_num}\n⏱ المده: {duration}\n\nشاهد المزيد من الحلقات:"
        await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^go_"))
async def on_navigate(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    # هنا نقوم باستدعاء نفس منطق إرسال الحلقة
    await on_start(client, query.message)

app.run()
