import os
import sqlite3
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)

# المتغيرات (تأكد من ضبطها في Railway)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0)) # القناة الخاصة (المصدر)
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "") # معرف القناة العامة (بـ @)
REQ_CHANNEL = os.environ.get("REQ_CHANNEL", "") # معرف قناة الاشتراك الإجباري (بـ @)

app = Client("CinemaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات =====
def db_execute(query, params=(), fetchone=False, fetchall=False):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone: res = cursor.fetchone()
    elif fetchall: res = cursor.fetchall()
    conn.commit()
    conn.close()
    return res

def init_db():
    db_execute('''CREATE TABLE IF NOT EXISTS videos 
                  (v_id TEXT PRIMARY KEY, duration TEXT, poster_id TEXT, 
                   ep_num INTEGER, title TEXT, quality TEXT)''')
    db_execute('''CREATE TABLE IF NOT EXISTS temp_state 
                  (admin_id INTEGER PRIMARY KEY, v_id TEXT, step TEXT)''')

init_db()

# ===== التحقق من الاشتراك الإجباري =====
async def check_subscribe(client, user_id):
    if not REQ_CHANNEL: return True
    try:
        member = await client.get_chat_member(REQ_CHANNEL, user_id)
        return True
    except UserNotParticipant:
        return False
    except Exception:
        return True

# ===== 1. استقبال الفيديو =====
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    
    db_execute("INSERT OR REPLACE INTO temp_state (admin_id, v_id, step) VALUES (?, ?, ?)", 
               (message.from_user.id, v_id, "waiting_poster"))
    
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\n🖼 الآن أرسل البوستر (صورة) ويمكنك إضافة العنوان في الوصف (اختياري):")

# ===== 2. استقبال البوستر =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def on_poster(client, message):
    state = db_execute("SELECT v_id, step FROM temp_state WHERE admin_id=?", (message.from_user.id,), fetchone=True)
    if not state or state[1] != "waiting_poster": return

    v_id = state[0]
    poster_id = message.photo.file_id
    title = message.caption if message.caption else "مشاهدة ممتعة"
    
    db_execute("INSERT OR REPLACE INTO videos (v_id, poster_id, title) VALUES (?, ?, ?)", (v_id, poster_id, title))
    db_execute("UPDATE temp_state SET step='waiting_ep' WHERE admin_id=?", (message.from_user.id,))
    
    await message.reply_text("🖼 تم حفظ البوستر.\n🔢 الآن أرسل **رقم الحلقة**:")

# ===== 3. استقبال رقم الحلقة =====
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command("start"))
async def on_ep(client, message):
    if not message.text.isdigit(): return
    state = db_execute("SELECT v_id, step FROM temp_state WHERE admin_id=?", (message.from_user.id,), fetchone=True)
    if not state or state[1] != "waiting_ep": return

    v_id = state[0]
    ep_num = int(message.text)
    
    db_execute("UPDATE videos SET ep_num=? WHERE v_id=?", (ep_num, v_id))
    db_execute("UPDATE temp_state SET step='waiting_quality' WHERE admin_id=?", (message.from_user.id,))
    
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("720p", callback_data=f"q_720p_{v_id}"),
        InlineKeyboardButton("1080p", callback_data=f"q_1080p_{v_id}")
    ]])
    await message.reply_text("✨ اختر الجودة لنشر الحلقة:", reply_markup=btns)

# ===== 4. اختيار الجودة والنشر التلقائي =====
@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    _, quality, v_id = query.data.split("_")
    db_execute("UPDATE videos SET quality=? WHERE v_id=?", (quality, v_id))
    db_execute("DELETE FROM temp_state WHERE admin_id=?", (query.from_user.id,))
    
    v = db_execute("SELECT title, ep_num, poster_id, duration FROM videos WHERE v_id=?", (v_id,), fetchone=True)
    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    
    if PUBLIC_CHANNEL:
        caption = f"🎬 **{v[0]}**\n🔢 الحلقة رقم: {v[1]}\n⏱ المده: {v[3]}\n✨ الجودة: {quality}"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❤️ أعجبني", callback_data="like"), InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]
        ])
        await client.send_photo(PUBLIC_CHANNEL, photo=v[2], caption=caption, reply_markup=markup)
    
    await query.message.edit_text(f"🚀 تم النشر بنجاح!\nالرابط: {watch_link}")

# ===== 5. عرض الحلقة للمستخدم (Start) =====
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if not await check_subscribe(client, message.from_user.id):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("إضغط هنا للاشتراك", url=f"https://t.me/{REQ_CHANNEL.replace('@','')}")]])
        return await message.reply_text(f"⚠️ يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من المشاهدة!\n\n{REQ_CHANNEL}", reply_markup=btn)

    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا محمد، تصفح القناة لمشاهدة الحلقات.")

    v_id = message.command[1]
    await send_video_logic(client, message.chat.id, v_id)

async def send_video_logic(client, chat_id, v_id):
    v = db_execute("SELECT poster_id, title, ep_num, duration, quality FROM videos WHERE v_id=?", (v_id,), fetchone=True)
    if not v: return await client.send_message(chat_id, "❌ الحلقة غير متوفرة.")

    # إرسال الفيديو من المصدر
    await client.copy_message(chat_id, CHANNEL_ID, int(v_id), protect_content=True)

    # جلب قائمة "شاهد المزيد" بناءً على نفس البوستر
    all_eps = db_execute("SELECT v_id, ep_num FROM videos WHERE poster_id=? ORDER BY ep_num ASC", (v[0],), fetchall=True)
    
    btns = []
    row = []
    for vid, num in all_eps:
        label = f"• {num} •" if vid == v_id else f"{num}"
        row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
        if len(row) == 4: btns.append(row); row = []
    if row: btns.append(row)

    caption = f"🎬 **{v[1]}**\n📦 حلقة رقم: {v[2]}\n⏱ المده: {v[3]}\n✨ الجودة: {v[4]}\n\n**شاهد المزيد من الحلقات:**"
    await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(btns))

@app.on_callback_query(filters.regex(r"^go_"))
async def on_nav(client, query):
    if not await check_subscribe(client, query.from_user.id):
        return await query.answer("يجب الاشتراك في القناة أولاً!", show_alert=True)
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await send_video_logic(client, query.from_user.id, v_id)

@app.on_callback_query(filters.regex("like"))
async def on_like(client, query):
    await query.answer("تمت الإضافة إلى المعجبات! ❤️")

app.run()
