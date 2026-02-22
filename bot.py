import os
import psycopg2  # أفضل من sqlite لضمان عدم ضياع البيانات
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (تُسحب من الإعدادات) =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0")
DATABASE_URL = os.environ.get("DATABASE_URL") # رابط قاعدة بيانات Railway
CHANNEL_ID = -1003547072209 # قناة Ramadan4kTV
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "@MoAlmohsen")

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دالة قاعدة البيانات =====
def db_query(query, params=(), commit=True, fetch=True):
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(query, params)
    if commit: conn.commit()
    res = cur.fetchall() if fetch else None
    cur.close()
    conn.close()
    return res

# إنشاء الجداول عند التشغيل
def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS videos 
                (v_id TEXT PRIMARY KEY, title TEXT, poster_id TEXT, status TEXT, ep_num INTEGER)''', commit=True, fetch=False)

try:
    init_db()
except:
    pass

# ===== استقبال المحتوى من قناة Ramadan4kTV =====

@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET status = 'waiting'", (v_id, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id})\nأرسل الآن البوستر مع اسم المسلسل في الوصف.")

@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل جديد"
    db_query("UPDATE videos SET title = %s, poster_id = %s, status = 'awaiting_ep' WHERE v_id = %s",
               (title, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم حفظ البوستر لـ **{title}**\n🔢 أرسل رقم الحلقة فقط:")

@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status = 'awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    
    v_id, title, poster_id = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num = %s, status = 'posted' WHERE v_id = %s", (ep_num, v_id), fetch=False)
    
    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    if PUBLIC_CHANNEL:
        try:
            caption = f"🎬 **{title}**\n🔹 **الحلقة رقم:** {ep_num}\n\n📥 **لمشاهدة الحلقة اضغط على الزر أدناه:**"
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
            await client.send_photo(chat_id=PUBLIC_CHANNEL, photo=poster_id, caption=caption, reply_markup=reply_markup)
            await message.reply_text(f"🚀 تم النشر بنجاح في {PUBLIC_CHANNEL}")
        except Exception as e:
            await message.reply_text(f"⚠️ فشل النشر التلقائي: {e}\nرابط الحلقة: {watch_link}")

# ===== نظام المشاهدة =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد! أرسل رابط الحلقة للمشاهدة.")
        return

    v_id = message.command[1]
    try:
        # إرسال الفيديو من القناة المصدر
        await client.copy_message(message.chat.id, CHANNEL_ID, int(v_id))
        
        # عرض حلقات أخرى لنفس المسلسل (اختياري)
        video_info = db_query("SELECT title FROM videos WHERE v_id = %s", (v_id,))
        if video_info:
            title = video_info[0][0]
            all_ep = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
            if len(all_ep) > 1:
                btns = []; row = []
                for vid, num in all_ep:
                    label = f"🔹 {num}" if vid == v_id else f"{num}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 5: btns.append(row); row = []
                if row: btns.append(row)
                await message.reply_text("📺 باقي الحلقات المتوفرة:", reply_markup=InlineKeyboardMarkup(btns))
    except:
        await message.reply_text("❌ الحلقة غير متوفرة أو لم يتم إضافة البوت كأدمن في القناة.")

if __name__ == "__main__":
    app.run()
