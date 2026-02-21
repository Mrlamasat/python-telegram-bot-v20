import os
import sqlite3
import logging
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ===== الإعدادات والتسجيل =====
logging.basicConfig(level=logging.INFO)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHANNEL = int(os.environ.get("ADMIN_CHANNEL", 0))  # قناة التخزين والتحكم
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")    # قناة النشر العامة (مثال: @MyChannel)
REQ_CHANNEL = os.environ.get("REQ_CHANNEL", "")       # يوزر قناة الاشتراك الإجباري (بدون @)

app = Client("AdvancedCinemaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def init_db():
    conn = sqlite3.connect("cinema.db")
    cursor = conn.cursor()
    # جدول الفيديوهات
    cursor.execute('''CREATE TABLE IF NOT EXISTS episodes 
                      (v_id TEXT PRIMARY KEY, file_id TEXT, poster_id TEXT, title TEXT, 
                       ep_num INTEGER, duration TEXT, quality TEXT, likes INTEGER DEFAULT 0)''')
    # جدول مؤقت لإدارة حالة الرفع
    cursor.execute('''CREATE TABLE IF NOT EXISTS temp_upload 
                      (admin_id INTEGER PRIMARY KEY, v_id TEXT, poster_id TEXT, 
                       title TEXT, ep_num INTEGER, duration TEXT, step TEXT)''')
    conn.commit()
    conn.close()

init_db()

# دالة مساعدة للتعامل مع القاعدة
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

# ===== فحص الاشتراك الإجباري =====
async def check_sub(client, user_id):
    if not REQ_CHANNEL: return True
    try:
        member = await client.get_chat_member(REQ_CHANNEL, user_id)
        return True
    except:
        return False

# ===== رحلة المشرف في قناة التخزين =====

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def handle_video_upload(client, message):
    # الخطوة 1: استلام الفيديو
    file_id = message.video.file_id if message.video else message.document.file_id
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else 0
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    
    db_query("INSERT OR REPLACE INTO temp_upload (admin_id, v_id, duration, step) VALUES (?, ?, ?, ?)", 
             (message.from_user.id, v_id, duration, "awaiting_poster"), commit=True)
    
    await message.reply_text(f"✅ تم استلام الفيديو.\n🖼 الآن أرسل **البوستر** (صورة) مع إمكانية إضافة وصف لها:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.photo)
async def handle_poster_upload(client, message):
    # الخطوة 2: استلام البوستر والوصف
    data = db_query("SELECT step FROM temp_upload WHERE admin_id=?", (message.from_user.id,), fetchone=True)
    if not data or data[0] != "awaiting_poster": return

    title = message.caption if message.caption else "بدون عنوان"
    db_query("UPDATE temp_upload SET poster_id=?, title=?, step=? WHERE admin_id=?", 
             (message.photo.file_id, title, "awaiting_ep_num", message.from_user.id), commit=True)
    
    await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل الآن **رقم الحلقة**:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def handle_text_inputs(client, message):
    user_id = message.from_user.id
    data = db_query("SELECT step, v_id FROM temp_upload WHERE admin_id=?", (user_id,), fetchone=True)
    if not data: return
    
    step, v_id = data
    
    if step == "awaiting_ep_num":
        if not message.text.isdigit():
            return await message.reply_text("❌ يرجى إرسال رقم فقط!")
        db_query("UPDATE temp_upload SET ep_num=?, step=? WHERE admin_id=?", (int(message.text), "awaiting_quality", user_id), commit=True)
        
        # عرض أزرار الجودة
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("480p", callback_data="q_480p"), InlineKeyboardButton("720p", callback_data="q_720p")],
            [InlineKeyboardButton("1080p", callback_data="q_1080p"), InlineKeyboardButton("4K", callback_data="q_4K")]
        ])
        await message.reply_text("✨ اختر جودة الحلقة:", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^q_"))
async def handle_quality_selection(client, query):
    quality = query.data.split("_")[1]
    user_id = query.from_user.id
    
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE admin_id=?", (user_id,), fetchone=True)
    if not data: return
    
    v_id, poster_id, title, ep_num, duration = data
    
    # حفظ في الجدول النهائي
    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (?, ?, ?, ?, ?, ?)",
             (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE admin_id=?", (user_id,), commit=True)

    # النشر في القناة العامة
    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    caption = (f"🎬 **{title}**\n\n"
               f"🔢 الحلقة: {ep_num}\n"
               f"⏱ المدة: {duration}\n"
               f"✨ الجودة: {quality}\n\n"
               "📥 اضغط على الزر أسفله للمشاهدة")
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("👍 أعجبني", callback_data=f"like_{v_id}"), 
         InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]
    ])
    
    if PUBLIC_CHANNEL:
        await client.send_photo(PUBLIC_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)
    
    await query.message.edit_text(f"🚀 تم نشر الحلقة {ep_num} بنجاح!")

# ===== التعامل مع المستخدمين (Start & Watch) =====

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا {message.from_user.mention}، استخدم الروابط من القناة للمشاهدة.")

    # فحص الاشتراك الإجباري
    is_subbed = await check_sub(client, message.from_user.id)
    if not is_subbed:
        return await message.reply_text(
            f"⚠️ عذراً، يجب عليك الاشتراك في قناتنا أولاً للمشاهدة.\n\n"
            f"قناة البوت: @{REQ_CHANNEL}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ اشتركت الآن", url=f"https://t.me/{message.chat.username}?start={message.command[1]}")]]))

    v_id = message.command[1]
    await send_episode(client, message.chat.id, v_id)

async def send_episode(client, chat_id, v_id):
    ep = db_query("SELECT poster_id, title, ep_num, duration, quality FROM episodes WHERE v_id=?", (v_id,), fetchone=True)
    if not ep:
        return await client.send_message(chat_id, "❌ الحلقة غير موجودة.")
    
    poster_id, title, ep_num, duration, quality = ep

    # إرسال الفيديو من القناة مباشرة (توفير استهلاك البيانات)
    await client.copy_message(chat_id, ADMIN_CHANNEL, int(v_id), protect_content=True)

    # جلب باقي الحلقات التي تملك نفس البوستر
    all_episodes = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=? ORDER BY ep_num ASC", (poster_id,), fetchall=True)
    
    buttons = []
    row = []
    for vid, num in all_episodes:
        label = f"▶️ {num}" if vid == v_id else f"{num}"
        row.append(InlineKeyboardButton(label, callback_data=f"show_{vid}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    caption = (f"🎬 **{title}**\n"
               f"📦 الحلقة رقم [{ep_num}]\n"
               f"⏱ المده الفعليه: {duration}\n"
               f"✨ الجودة: {quality}\n\n"
               "👇 **شاهد المزيد من الحلقات:**")
    
    await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^(show|like)_"))
async def handle_interactions(client, query):
    action, v_id = query.data.split("_")
    
    if action == "show":
        await query.message.delete()
        await send_episode(client, query.from_user.id, v_id)
    
    elif action == "like":
        # تحديث بسيط للإعجاب (يمكن تطويره ليكون لكل مستخدم)
        await query.answer("❤️ شكراً على تقييمك!")

print("✅ البوت يعمل بكفاءة...")
app.run()
