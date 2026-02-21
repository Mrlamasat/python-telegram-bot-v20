import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# إعداد التسجيل لمتابعة أداء البوت في Railway
logging.basicConfig(level=logging.INFO)

# الإعدادات - يرجى وضعها في متغيرات البيئة في Railway
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PRIVATE_STORAGE = -1003547072209  # قناتك الخاصة
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")  # قناة النشر (@channel)
REQ_CHANNEL = os.environ.get("REQ_CHANNEL", "")  # قناة الاشتراك الإجباري (@channel)

app = Client("CinemaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- إدارة قاعدة البيانات ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone: res = cursor.fetchone()
    elif fetchall: res = cursor.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

# إنشاء الجداول المطلوبة
db_query('''CREATE TABLE IF NOT EXISTS videos 
            (v_id TEXT PRIMARY KEY, duration TEXT, poster_id TEXT, 
             title TEXT, ep_num INTEGER, quality TEXT)''', commit=True)

db_query('''CREATE TABLE IF NOT EXISTS temp_state 
            (admin_id INTEGER PRIMARY KEY, v_id TEXT, step TEXT)''', commit=True)

# --- فحص الاشتراك الإجباري ---
async def check_sub(client, user_id):
    if not REQ_CHANNEL: return True
    try:
        await client.get_chat_member(REQ_CHANNEL, user_id)
        return True
    except UserNotParticipant:
        return False
    except:
        return True

# --- 1. استقبال الفيديو ---
@app.on_message(filters.chat(PRIVATE_STORAGE) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    dur_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{dur_sec // 60}:{dur_sec % 60:02d}"
    
    db_query("INSERT OR REPLACE INTO temp_state (admin_id, v_id, step) VALUES (?, ?, ?)", 
             (message.from_user.id, v_id, "get_poster"), commit=True)
    db_query("INSERT OR REPLACE INTO videos (v_id, duration) VALUES (?, ?)", (v_id, duration), commit=True)
    
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\n🖼 الآن أرسل **البوستر** (صورة) واكتب العنوان في الوصف إن أردت:")

# --- 2. استقبال البوستر (العنوان اختياري) ---
@app.on_message(filters.chat(PRIVATE_STORAGE) & filters.photo)
async def on_poster(client, message):
    state = db_query("SELECT v_id, step FROM temp_state WHERE admin_id=?", (message.from_user.id,), fetchone=True)
    if not state or state[1] != "get_poster": return

    v_id = state[0]
    title = message.caption if message.caption else "مشاهدة ممتعة"
    
    db_query("UPDATE videos SET poster_id=?, title=? WHERE v_id=?", (message.photo.file_id, title, v_id), commit=True)
    db_query("UPDATE temp_state SET step='get_ep' WHERE admin_id=?", (message.from_user.id,), commit=True)
    
    await message.reply_text("🖼 تم حفظ البوستر.\n🔢 أرسل الآن **رقم الحلقة**:")

# --- 3. استقبال رقم الحلقة ---
@app.on_message(filters.chat(PRIVATE_STORAGE) & filters.text & ~filters.command("start"))
async def on_ep(client, message):
    if not message.text.isdigit(): return
    state = db_query("SELECT v_id, step FROM temp_state WHERE admin_id=?", (message.from_user.id,), fetchone=True)
    if not state or state[1] != "get_ep": return

    v_id = state[0]
    db_query("UPDATE videos SET ep_num=? WHERE v_id=?", (int(message.text), v_id), commit=True)
    db_query("UPDATE temp_state SET step='get_quality' WHERE admin_id=?", (message.from_user.id,), commit=True)
    
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("720p", callback_data=f"q_{v_id}_720p"),
        InlineKeyboardButton("1080p", callback_data=f"q_{v_id}_1080p")
    ]])
    await message.reply_text("✨ اختر الجودة للنشر:", reply_markup=btns)

# --- 4. اختيار الجودة والنشر التلقائي ---
@app.on_callback_query(filters.regex(r"^q_"))
async def on_publish(client, query):
    _, v_id, quality = query.data.split("_")
    db_query("UPDATE videos SET quality=? WHERE v_id=?", (quality, v_id), commit=True)
    db_query("DELETE FROM temp_state WHERE admin_id=?", (query.from_user.id,), commit=True)
    
    v = db_query("SELECT title, ep_num, poster_id, duration FROM videos WHERE v_id=?", (v_id,), fetchone=True)
    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    
    if PUBLIC_CHANNEL:
        caption = f"🎬 **{v[0]}**\n🔢 الحلقة: {v[1]}\n⏱ المده: {v[3]}\n✨ الجودة: {quality}"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❤️ أعجبني", callback_data="like_it"), 
             InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]
        ])
        await client.send_photo(PUBLIC_CHANNEL, photo=v[2], caption=caption, reply_markup=markup)
    
    await query.message.edit_text(f"🚀 تم النشر بنجاح!\nالرابط: {watch_link}")

# --- 5. تشغيل الفيديو وقائمة الحلقات ---
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if not await check_sub(client, message.from_user.id):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("إضغط هنا للاشتراك", url=f"https://t.me/{REQ_CHANNEL.replace('@','')}")]])
        return await message.reply_text(f"⚠️ يجب الاشتراك في القناة أولاً لتتمكن من المشاهدة!\n{REQ_CHANNEL}", reply_markup=btn)

    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد! استخدم روابط المشاهدة من القناة.")

    v_id = message.command[1]
    await send_content(client, message.chat.id, v_id)

async def send_content(client, chat_id, v_id):
    v = db_query("SELECT poster_id, title, ep_num, duration, quality FROM videos WHERE v_id=?", (v_id,), fetchone=True)
    if not v: return await client.send_message(chat_id, "❌ عذراً، الحلقة غير متوفرة.")

    # إرسال الفيديو من القناة الخاصة
    await client.copy_message(chat_id, PRIVATE_STORAGE, int(v_id), protect_content=True)

    # جلب قائمة الحلقات بناءً على نفس البوستر
    all_eps = db_query("SELECT v_id, ep_num FROM videos WHERE poster_id=? ORDER BY ep_num ASC", (v[0],), fetchall=True)
    
    btns = []
    row = []
    for vid, num in all_eps:
        label = f"▶️ {num}" if vid == v_id else f"{num}"
        row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
        if len(row) == 4: btns.append(row); row = []
    if row: btns.append(row)

    caption = f"🎬 **{v[1]}**\n📦 حلقة: {v[2]}\n⏱ مده: {v[3]}\n✨ جودة: {v[4]}\n\n**شاهد المزيد من الحلقات:**"
    await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(btns))

@app.on_callback_query(filters.regex(r"^go_"))
async def on_navigate(client, query):
    if not await check_sub(client, query.from_user.id):
        return await query.answer("اشترك في القناة أولاً!", show_alert=True)
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await send_content(client, query.from_user.id, v_id)

@app.on_callback_query(filters.regex("like_it"))
async def on_like(client, query):
    await query.answer("شكراً لك! ❤️")

app.run()
