import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -----------------------------
# 🔐 إعدادات من Environment Variables
# -----------------------------
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")
ADMIN_CHANNEL  = int(os.environ.get("ADMIN_CHANNEL", 0))
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")

if not all([SESSION_STRING, DATABASE_URL, API_ID, API_HASH, ADMIN_CHANNEL, PUBLIC_CHANNELS]):
    raise ValueError("❌ أحد متغيرات البيئة مفقود. تحقق من Secrets في GitHub.")

# -----------------------------
# 🔹 إعداد البوت
# -----------------------------
app = Client(
    "userbot_session",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    in_memory=True
)

# -----------------------------
# 📌 دالات مساعدة
# -----------------------------
def hide_text(text):
    return "‌".join(list(text)) if text else "‌"

def center_style(text):
    spacer = "ㅤ" * 8
    return f"{spacer}{text}{spacer}"

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None)
        if commit: conn.commit()
        cur.close()
        return res
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# -----------------------------
# 1️⃣ رفع الحلقة + البوستر + رقم الحلقة
# -----------------------------
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def handle_video(client, message):
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query(
        "INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') "
        "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
        (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"), commit=True
    )
    await message.reply_text("✅ استلمت الفيديو. أرسل البوستر الآن مع اسم المسلسل في الوصف.")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def handle_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return
    if not message.caption:
        return await message.reply_text("⚠️ اكتب اسم المسلسل في وصف الصورة.")
    
    f_id = message.photo.file_id if message.photo else message.document.file_id
    db_query(
        "UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s",
        (f_id, message.caption, message.chat.id), commit=True
    )
    await message.reply_text(f"✅ تم الربط بمسلسل: **{message.caption}**. أرسل رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start", "fix"]))
async def handle_ep_number(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep": return
    if not message.text.isdigit(): return
    
    db_query(
        "UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s",
        (int(message.text), message.chat.id), commit=True
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p", callback_data="q_1080p"),
                                InlineKeyboardButton("720p", callback_data="q_720p")]])
    await message.reply_text(f"🎬 حلقة {message.text} جاهزة. اختر الجودة للنشر:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    db_query(
        "INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) "
        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (v_id) DO UPDATE "
        "SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality",
        (data['v_id'], data['poster_id'], data['title'], data['ep_num'], data['duration'], quality), commit=True
    )
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['v_id']}".replace(" ", "")
    
    h_title = hide_text(data['title'])
    hidden_cap = f"**{center_style('🎬 ' + h_title)}**\n**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**\n**{center_style('⚙️ الجودة: ' + quality)}**"
    
    for ch in PUBLIC_CHANNELS:
        try:
            await client.send_photo(ch.strip(), photo=data['poster_id'], caption=hidden_cap,
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر في القنوات.")

# -----------------------------
# 2️⃣ نظام start (مشاهدة الحلقة)
# -----------------------------
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("🎬 أهلاً بك. تفضل بزيارة قناتنا.")
    
    param = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (str(param),), fetchone=True)
    if not data:
        return await message.reply_text("❌ الحلقة غير موجودة.")
    
    clean_name = data['title'].replace('‌','').strip()
    related = db_query("SELECT v_id, ep_num FROM episodes WHERE title LIKE %s ORDER BY ep_num ASC",
                       (f"%{clean_name}%",), fetchall=True)
    
    bot_info = await client.get_me()
    buttons, row = [], []
    if related:
        for ep in related:
            label = f"🔹 {ep['ep_num']}" if str(ep['v_id']) == str(param) else f"{ep['ep_num']}"
            ep_link = f"https://t.me/{bot_info.username}?start={ep['v_id']}".replace(" ", "")
            row.append(InlineKeyboardButton(label, url=ep_link))
            if len(row) == 5: buttons.append(row); row = []
        if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🍿 شاهد المزيد", url="https://t.me/MoAlmohsen")])
    
    final_cap = f"**{center_style('🎬 ' + clean_name)}**\n**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**"
    
    try:
        await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(data['v_id']), caption=final_cap,
                                  reply_markup=InlineKeyboardMarkup(buttons))
    except:
        await message.reply_text("⚠️ تأكد من إضافة البوت كأدمن في القناة الإدارية.")

# -----------------------------
# ▶️ تشغيل البوت
# -----------------------------
if __name__ == "__main__":
    print("🚀 البوت يعمل الآن على GitHub Actions...")
    app.run()
