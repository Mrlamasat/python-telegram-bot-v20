import os
import sqlite3
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# الإعدادات
logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# --- المعرفات التي أرسلتها يا محمد ---
ADMIN_CHANNEL = -1003547072209  # قناة التخزين (الخاصة)
PUBLIC_CHANNEL = "@RamadanSeries26"  # القناة العامة للنشر
REQ_CHANNEL = "RamadanSeries26" # قناة الاشتراك الإجباري (بدون @)

app = Client("CinemaBot_Final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- قاعدة البيانات المحلية ---
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
    await message.reply_text("✅ تم استلام الفيديو\n🖼 الآن أرسل (البوستر) :")

# --- 2. استلام البوستر (يدعم WebP والصور العادية) ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker | filters.document))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_poster":
        return

    try:
        if message.photo:
            photo_id = message.photo.file_id
        elif message.sticker:
            photo_id = message.sticker.file_id
        elif message.document and "image" in (message.document.mime_type or ""):
            photo_id = message.document.file_id
        else: return

        title = message.caption if message.caption else ""
        db_query("UPDATE temp_upload SET poster_id = ?, title = ?, step = ? WHERE chat_id = ?", 
                 (photo_id, title, "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
        
        await message.reply_text("🖼 تم حفظ البوستر بنجاح\n🔢 أرسل الآن رقم الحلقة:")
    except Exception as e:
        await message.reply_text("⚠️ خطأ في الصورة، أعد المحاولة.")

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

# --- 4. النشر النهائي الذكي ---
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
    if title and title.strip(): caption += f"🎬 **{title}**\n"
    caption += f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر لمشاهدة الحلقة"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
    
    # محاولة النشر في القناة العامة
    try:
        await client.send_photo(PUBLIC_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)
    except:
        try:
            await client.send_document(PUBLIC_CHANNEL, document=poster_id, caption=caption, reply_markup=markup)
        except:
            await client.send_message(PUBLIC_CHANNEL, caption, reply_markup=markup)
    
    await query.message.edit_text("🚀 تم نشر الحلقة بنجاح في القناة العامة!")

# --- فحص الاشتراك وعرض الفيديو للمستخدم ---
async def is_subscribed(client, user_id):
    try:
        member = await client.get_chat_member(PUBLIC_CHANNEL, user_id)
        return member.status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except: return False

async def send_episode_details(client, chat_id, v_id):
    ep = db_query("SELECT poster_id, title, ep_num, duration, quality FROM episodes WHERE v_id=?", (v_id,), fetchone=True)
    try:
        await client.copy_message(chat_id, ADMIN_CHANNEL, int(v_id), protect_content=True)
        if ep:
            poster_id, title, ep_num, duration, quality = ep
            all_eps = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=? ORDER BY ep_num ASC", (poster_id,), fetchall=True)
            buttons = []
            row = []
            for vid, num in all_eps:
                label = f"⭐ {num}" if vid == v_id else f"{num}"
                row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
                if len(row) == 4: buttons.append(row); row = []
            if row: buttons.append(row)

            header = f"🎬 **{title}**\n" if title and title.strip() else ""
            caption = f"{header}📦 حلقة رقم: {ep_num}\n⏱ المده: {duration}\n✨ الجودة: {quality}\n\n📖 شاهد المزيد من الحلقات:"
            await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons))
    except:
        await client.send_message(chat_id, "❌ عذراً، لم يتم العثور على هذه الحلقة.")

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if not await is_subscribed(client, message.from_user.id):
        return await message.reply_text(f"⚠️ يجب الاشتراك في القناة أولاً لمشاهدة الأفلام والمسلسلات:\n\n{PUBLIC_CHANNEL}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 اضغط هنا للاشتراك", url=f"https://t.me/{REQ_CHANNEL}")]]))
    if len(message.command) > 1:
        await send_episode_details(client, message.chat.id, message.command[1])
    else:
        await message.reply_text("أهلاً بك يا محمد! البوت جاهز للعمل.")

@app.on_callback_query(filters.regex(r"^go_"))
async def on_navigate(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await send_episode_details(client, query.from_user.id, v_id)

app.run()
