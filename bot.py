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
    raise ValueError("❌ أحد متغيرات البيئة مفقود.")

app = Client("userbot_session", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)

# -----------------------------
# 📌 دالات قاعدة البيانات
# -----------------------------
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
# 1️⃣ نظام الرفع (إضافة الحلقات)
# -----------------------------
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def handle_video(client, message):
    v_id = str(message.id)
    db_query(
        "INSERT INTO temp_upload (chat_id, v_id, step) VALUES (%s, %s, 'awaiting_poster') "
        "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
        (message.chat.id, v_id), commit=True
    )
    await message.reply_text("✅ استلمت الفيديو. أرسل البوستر الآن مع اسم المسلسل في الوصف.")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def handle_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return
    if not message.caption: return await message.reply_text("⚠️ اكتب اسم المسلسل في وصف الصورة.")
    
    f_id = message.photo.file_id if message.photo else message.document.file_id
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s",
             (f_id, message.caption, message.chat.id), commit=True)
    await message.reply_text(f"✅ تم ربط المسلسل: **{message.caption}**. أرسل رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start"]))
async def handle_ep_number(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep" or not message.text.isdigit(): return
    
    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s",
             (int(message.text), message.chat.id), commit=True)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p", callback_data="q_1080p"),
                                InlineKeyboardButton("720p", callback_data="q_720p")]])
    await message.reply_text(f"🎬 حلقة {message.text} جاهزة. اختر الجودة للنشر:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, quality) VALUES (%s,%s,%s,%s,%s) "
             "ON CONFLICT (v_id) DO UPDATE SET quality=EXCLUDED.quality",
             (data['v_id'], data['poster_id'], data['title'], data['ep_num'], quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    
    bot = await client.get_me()
    link = f"https://t.me/{bot.username}?start={data['v_id']}" # الرابط المعدل
    
    for ch in PUBLIC_CHANNELS:
        try:
            cap = f"**🎬 {data['title']}**\n**🔢 حلقة رقم: {data['ep_num']}**\n**⚙️ الجودة: {quality}**"
            await client.send_photo(ch.strip(), photo=data['poster_id'], caption=cap,
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر بنجاح.")

# -----------------------------
# 2️⃣ نظام المشاهدة (start) - تم تعديل هذا الجزء
# -----------------------------
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    # إذا كان الرابط يحتوي على معرف الحلقة
    if len(message.command) > 1:
        param = message.command[1]
        data = db_query("SELECT * FROM episodes WHERE v_id=%s", (str(param),), fetchone=True)
        
        if data:
            cap = f"**🎬 {data['title']}**\n**🔢 حلقة رقم: {data['ep_num']}**"
            try:
                # إرسال الفيديو من القناة الإدارية للمستخدم مباشرة
                await client.copy_message(chat_id=message.chat.id, from_chat_id=ADMIN_CHANNEL, 
                                          message_id=int(data['v_id']), caption=cap)
                return
            except Exception as e:
                return await message.reply_text("⚠️ تأكد من أن البوت مسؤول (Admin) في القناة الإدارية.")

    # الرد الافتراضي إذا لم يجد حلقة أو ضغط start فقط
    await message.reply_text("🎬 أهلاً بك يا محمد في بوت المشاهدة.\nتفضل بزيارة قناتنا: @MoAlmohsen")

if __name__ == "__main__":
    print("🚀 البوت يعمل الآن بنظام الروابط الجديد...")
    app.run()
