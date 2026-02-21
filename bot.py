import os
import sqlite3
import logging
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ===== الإعدادات (تأكد من ضبطها في Railway) =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))  # قناة التخزين
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "") # يوزر القناة بدون @
FORCE_SUB = os.environ.get("FORCE_SUB", "") # يوزر قناة الاشتراك الإجباري بدون @

# نظام تخزين مؤقت للحالات (لحفظ الخطوات)
user_steps = {}

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, poster_id TEXT, 
                       title TEXT, ep_num INTEGER, quality TEXT, likes INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=True):
    with sqlite3.connect("bot_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.fetchall() if fetch else None

# ===== فحص الاشتراك الإجباري =====
async def is_subscribed(client, user_id):
    if not FORCE_SUB: return True
    try:
        member = await client.get_chat_member(FORCE_SUB, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ===== استقبال الفيديو (الخطوة 1) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    mins, secs = divmod(duration_sec, 60)
    duration = f"{mins}:{secs:02d} دقيقة"
    
    user_steps[message.from_user.id] = {"v_id": v_id, "duration": duration, "step": "poster"}
    await message.reply_text(f"✅ تم استلام الفيديو.\n🖼 الآن أرسل **صورة البوستر**.")

# ===== استقبال البوستر والعنوان (الخطوة 2) =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    user_id = message.from_user.id
    if user_id not in user_steps or user_steps[user_id]["step"] != "poster": return

    user_steps[user_id]["poster_id"] = message.photo.file_id
    user_steps[user_id]["title"] = message.caption if message.caption else "بدون عنوان"
    user_steps[user_id]["step"] = "ep_num"
    
    await message.reply_text("🔢 أرسل الآن **رقم الحلقة**:")

# ===== استقبال رقم الحلقة (الخطوة 3) =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command("start"))
async def receive_ep_num(client, message):
    user_id = message.from_user.id
    if user_id not in user_steps or user_steps[user_id]["step"] != "ep_num": return
    
    if not message.text.isdigit():
        await message.reply_text("⚠️ يرجى إرسال رقم فقط.")
        return

    user_steps[user_id]["ep_num"] = int(message.text)
    user_steps[user_id]["step"] = "quality"

    # أزرار الجودة
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("720p", callback_data="q_720p"),
        InlineKeyboardButton("1080p", callback_data="q_1080p"),
        InlineKeyboardButton("4K", callback_data="q_4k")
    ]])
    await message.reply_text("✨ اختر **الجودة**:", reply_markup=btn)

# ===== حفظ ونشر الحلقة (الخطوة الأخيرة) =====
@app.on_callback_query(filters.regex(r"^q_"))
async def save_and_post(client, query):
    user_id = query.from_user.id
    if user_id not in user_steps: return

    data = user_steps[user_id]
    quality = query.data.split("_")[1]
    
    db_execute("INSERT INTO videos (v_id, duration, poster_id, title, ep_num, quality) VALUES (?,?,?,?,?,?)",
               (data["v_id"], data["duration"], data["poster_id"], data["title"], data["ep_num"], quality), fetch=False)

    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={data['v_id']}"

    # تنسيق الرسالة للنشر
    caption = (f"🎬 **{data['title']}**\n"
               f"🔢 الحلقة: {data['ep_num']}\n"
               f"⏱ المدة: {data['duration']}\n"
               f"✨ الجودة: {quality}\n")

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👍 0", callback_data=f"like_{data['v_id']}"), 
         InlineKeyboardButton("▶️ شاهد الحلقة", url=watch_link)]
    ])

    if PUBLIC_CHANNEL:
        await client.send_photo(PUBLIC_CHANNEL, data["poster_id"], caption=caption, reply_markup=markup)
    
    await query.message.edit_text("🚀 تم حفظ ونشر الحلقة بنجاح!")
    del user_steps[user_id]

# ===== معالج التشغيل والاستماع =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if not await is_subscribed(client, message.from_user.id):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{FORCE_SUB}")]])
        await message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة المحتوى.", reply_markup=btn)
        return

    if len(message.command) > 1:
        v_id = message.command[1]
        await send_video_content(client, message.chat.id, v_id)
    else:
        await message.reply_text("🎬 أهلاً بك في بوت المشاهدة.. أرسل رابط الحلقة.")

async def send_video_content(client, chat_id, v_id):
    video = db_execute("SELECT poster_id, duration, title, ep_num, quality FROM videos WHERE v_id=?", (v_id,))
    if not video:
        await client.send_message(chat_id, "❌ الحلقة غير موجودة.")
        return

    poster_id, duration, title, ep_num, quality = video[0]
    
    # 1. إرسال الفيديو
    await client.copy_message(chat_id, CHANNEL_ID, int(v_id), protect_content=True)

    # 2. جلب كافة الحلقات المرتبطة بنفس البوستر
    all_eps = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? ORDER BY ep_num ASC", (poster_id,))
    
    buttons = []
    row = []
    for vid, num in all_eps:
        label = f"• {num} •" if vid == v_id else str(num)
        row.append(InlineKeyboardButton(label, callback_data=f"show_{vid}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    caption = f"📖 **شاهد المزيد من الحلقات ( {title} )**"
    await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^show_"))
async def switch_ep(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await send_video_content(client, query.from_user.id, v_id)

app.run()
