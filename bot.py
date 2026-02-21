import os
import sqlite3
import logging
import asyncio
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait

# ===== إعدادات التسجيل لـ Railway =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (ضبطها في Railway Variables) =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))  # قناة التخزين الخاصة
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "") # يوزر قناة النشر (بدون @)
FORCE_SUB = os.environ.get("FORCE_SUB", "") # يوزر قناة الاشتراك الإجباري (بدون @)

# نظام تتبع الحالات لمنع تداخل الطلبات
user_steps = {}

app = Client("BottemoBot_New", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos 
                      (v_id TEXT PRIMARY KEY, duration TEXT, poster_id TEXT, 
                       title TEXT, ep_num INTEGER, quality TEXT)''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=True):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.fetchall() if fetch else None

# ===== فحص الاشتراك الإجباري =====
async def check_subscription(client, user_id):
    if not FORCE_SUB: return True
    try:
        member = await client.get_chat_member(FORCE_SUB, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ===== 1. استقبال الفيديو (قناة التخزين) =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def on_video_receive(client, message):
    v_id = str(message.id)
    # حساب المدة
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    mins, secs = divmod(duration_sec, 60)
    duration_str = f"{mins}:{secs:02d} دقيقة"
    
    user_steps[message.from_user.id] = {
        "v_id": v_id, 
        "duration": duration_str, 
        "step": "waiting_poster"
    }
    await message.reply_text(f"📥 تم استلام الفيديو (ID: {v_id})\n🖼 أرسل الآن **صورة البوستر** (يمكنك إضافة عنوان المسلسل في وصف الصورة).")

# ===== 2. استقبال البوستر والعنوان =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def on_poster_receive(client, message):
    user_id = message.from_user.id
    if user_id not in user_steps or user_steps[user_id]["step"] != "waiting_poster":
        return

    user_steps[user_id]["poster_id"] = message.photo.file_id
    user_steps[user_id]["title"] = message.caption if message.caption else "مسلسل غير مسمى"
    user_steps[user_id]["step"] = "waiting_ep_num"
    
    await message.reply_text(f"🖼 تم حفظ البوستر: **{user_steps[user_id]['title']}**\n🔢 أرسل الآن **رقم الحلقة**:")

# ===== 3. استقبال رقم الحلقة واختيار الجودة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command("start"))
async def on_ep_num_receive(client, message):
    user_id = message.from_user.id
    if user_id not in user_steps or user_steps[user_id]["step"] != "waiting_ep_num":
        return
    
    if not message.text.isdigit():
        await message.reply_text("⚠️ يرجى إرسال رقم الحلقة (أرقام فقط).")
        return

    user_steps[user_id]["ep_num"] = int(message.text)
    user_steps[user_id]["step"] = "waiting_quality"

    # أزرار اختيار الجودة
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("720p", callback_data="set_720p"),
         InlineKeyboardButton("1080p", callback_data="set_1080p")],
        [InlineKeyboardButton("4K Ultra HD", callback_data="set_4k")]
    ])
    await message.reply_text("✨ اختر **جودة الحلقة** ليتم النشر:", reply_markup=btns)

# ===== 4. النشر النهائي في القناة =====
@app.on_callback_query(filters.regex(r"^set_"))
async def finalize_post(client, query):
    user_id = query.from_user.id
    if user_id not in user_steps: return

    quality = query.data.split("_")[1]
    data = user_steps[user_id]

    # حفظ في قاعدة البيانات
    db_execute("INSERT OR REPLACE INTO videos (v_id, duration, poster_id, title, ep_num, quality) VALUES (?,?,?,?,?,?)",
               (data["v_id"], data["duration"], data["poster_id"], data["title"], data["ep_num"], quality), fetch=False)

    bot_user = (await client.get_me()).username
    watch_link = f"https://t.me/{bot_user}?start={data['v_id']}"

    # تنسيق رسالة القناة العامة
    caption = (f"🎬 **{data['title']}**\n"
               f"🔢 الحلقة رقم: **[{data['ep_num']}]**\n"
               f"⏱ المـدة: {data['duration']}\n"
               f"✨ الجودة: {quality}\n\n"
               f"📥 اضغط على الزر بالأسفل للمشاهدة")

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ اضغط هنا لمشاهدة الحلقة", url=watch_link)],
        [InlineKeyboardButton("👍 أعجبني", callback_data="like_post")]
    ])

    try:
        if PUBLIC_CHANNEL:
            await client.send_photo(PUBLIC_CHANNEL, data["poster_id"], caption=caption, reply_markup=markup)
            await query.message.edit_text("🚀 تم النشر بنجاح في القناة العامة!")
        else:
            await query.message.edit_text(f"✅ تم الحفظ بنجاح!\nرابط الحلقة: {watch_link}")
    except Exception as e:
        await query.message.edit_text(f"⚠️ خطأ أثناء النشر: {e}")
    
    del user_steps[user_id]

# ===== معالج الدخول للبوت (المشاهدة) =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    # فحص الاشتراك الإجباري
    if not await check_subscription(client, message.from_user.id):
        join_btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك في القناة أولاً", url=f"https://t.me/{FORCE_SUB}")]])
        await message.reply_text("❌ عذراً يا محمد، يجب عليك الاشتراك في القناة لتتمكن من استخدام البوت.", reply_markup=join_btn)
        return

    if len(message.command) > 1:
        v_id = message.command[1]
        await send_episode(client, message.chat.id, v_id)
    else:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المشاهدة الرسمي.")

async def send_episode(client, chat_id, v_id):
    res = db_execute("SELECT poster_id, duration, title, ep_num, quality FROM videos WHERE v_id=?", (v_id,))
    if not res:
        await client.send_message(chat_id, "❌ عذراً، هذه الحلقة غير متوفرة أو تم حذفها.")
        return

    poster_id, duration, title, ep_num, quality = res[0]

    # إرسال الفيديو من قناة التخزين
    try:
        await client.copy_message(chat_id, CHANNEL_ID, int(v_id), protect_content=True)
    except:
        await client.send_message(chat_id, "❌ خطأ في جلب الفيديو من التخزين.")
        return

    # جلب قائمة الحلقات لنفس البوستر (نفس المسلسل)
    all_eps = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? ORDER BY ep_num ASC", (poster_id,))
    
    buttons = []
    row = []
    for vid, num in all_eps:
        # وضع علامة تمييز على الحلقة الحالية
        btn_text = f"• {num} •" if vid == v_id else f"{num}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"view_{vid}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    caption = f"🎬 **{title}** - حلقة {ep_num}\n\n📖 **شاهد المزيد من الحلقات:**"
    await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons))

# تنقل بين الحلقات من داخل البوت
@app.on_callback_query(filters.regex(r"^view_"))
async def navigate_episodes(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await send_episode(client, query.from_user.id, v_id)

# تشغيل البوت مع معالجة الـ FloodWait
if __name__ == "__main__":
    print("✅ البوت قيد التشغيل...")
    try:
        app.run()
    except FloodWait as e:
        import time
        print(f"⚠️ تليجرام فرض حظر مؤقت. سننتظر {e.value} ثانية...")
        time.sleep(e.value)
        app.run()
