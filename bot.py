import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# الإعدادات (تأكد من كتابة الأرقام بشكل صحيح في متغيرات البيئة)
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# دالة قاعدة البيانات (بسيطة ومستقرة)
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return None

# دالة التنسيق المنقط
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text.replace(" ", "  ")))

# دالة تنظيف النص للبحث
def clean_for_search(text):
    if not text: return ""
    text = text.replace(".", "").replace(" ", "")
    text = re.sub(r'[أإآ]', 'ا', text).replace('ة', 'ه').replace('ى', 'ي')
    return text.lower()

# 1. استقبال الفيديو في المصدر
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') and media.duration else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text("✅ تم استلام الفيديو. أرسل الآن البوستر واكتب الاسم في وصفه.")

# 2. استقبال البوستر والاسم
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption
    if not title:
        await message.reply_text("⚠️ خطأ: أرسل البوستر مع كتابة الاسم في الوصف!")
        return
    
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 الاسم: {title}\nاختر الجودة:", reply_markup=markup)

# 3. الجودة ثم رقم الحلقة والنشر
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن رقم الحلقة فقط.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command("start"))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text
    
    caption = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\nالحلقة: [{ep_num}]\nالجودة: [{q}]\nالمدة: [{dur}]"
    me = await client.get_me()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    try:
        # النشر النهائي
        post = await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
        db_query("UPDATE videos SET ep_num=%s, status='posted', post_id=%s WHERE v_id=%s", (ep_num, post.id, v_id), fetch=False)
        await message.reply_text(f"🚀 تم النشر بنجاح: {title}")
    except Exception as e:
        await message.reply_text(f"❌ فشل النشر: {e}")

# 4. نظام البحث في الخاص (ذكي ومستقر)
@app.on_message(filters.private & filters.text & ~filters.command("start"))
async def search_handler(client, message):
    user_query = clean_for_search(message.text)
    if len(user_query) < 2: return
    
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if user_query in clean_for_search(t[0])]
    
    if matches:
        btns = [[InlineKeyboardButton(f"🎬 {m}", callback_data=f"lst_{m[:40]}")] for m in matches[:10]]
        await message.reply_text("🔍 نتائج البحث:", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await message.reply_text("❌ لم أجد نتائج.")

@app.on_callback_query(filters.regex("^lst_"))
async def list_episodes(client, cb):
    title = cb.data.replace("lst_", "")
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (f"{title}%",))
    btns, row = [], []
    for vid, ep in (res or []):
        row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"snd_{vid}"))
        if len(row) == 3: btns.append(row); row = []
    if row: btns.append(row)
    await cb.message.edit_text(f"📺 حلقات {title}:", reply_markup=InlineKeyboardMarkup(btns))

@app.on_callback_query(filters.regex("^snd_"))
async def send_video(client, cb):
    v_id = cb.data.replace("snd_", "")
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
    if res:
        t, e = res[0]
        await client.copy_message(cb.message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"📺 {obfuscate_visual(t)} - حلقة {e}")

# 5. البداية (Start)
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
        if res:
            t, e = res[0]
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"📺 {obfuscate_visual(t)} - حلقة {e}")
    else:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}، اكتب اسم المسلسل للبحث.")

# تشغيل البوت
if __name__ == "__main__":
    # إنشاء الجدول لمرة واحدة لضمان الاستقرار
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS videos (v_id VARCHAR(50) PRIMARY KEY, title VARCHAR(255), poster_id VARCHAR(255), duration VARCHAR(20), quality VARCHAR(10), ep_num VARCHAR(10), status VARCHAR(50) DEFAULT 'waiting', post_id BIGINT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    cur.close()
    conn.close()
    app.run()
