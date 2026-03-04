import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ===== الإعدادات الأساسية =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# جلب البيانات من متغيرات البيئة
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# المعرفات كأرقام صحيحة (Integers) - ضروري جداً لتجنب خطأ get_peer_type
SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307 
FORCE_SUB_CHANNEL = -1003894735143 

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دوال قاعدة البيانات =====
def init_database():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                v_id VARCHAR(50) PRIMARY KEY,
                title VARCHAR(255),
                poster_id VARCHAR(255),
                duration VARCHAR(20),
                quality VARCHAR(10),
                ep_num VARCHAR(10),
                status VARCHAR(50) DEFAULT 'waiting',
                post_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("✅ Database Initialized")
    except Exception as e:
        logger.error(f"❌ Database Init Error: {e}")

def db_query(query, params=(), fetch=True):
    conn = None
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
        return result
    except Exception as e:
        logger.error(f"❌ Query Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()

# ===== دوال المعالجة =====
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text.replace(" ", "  ")))

def clean_for_search(text):
    if not text: return ""
    text = text.replace(".", "").replace(" ", "")
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ة]', 'ه', text)
    text = re.sub(r'[ى]', 'ي', text)
    return text.lower()

# ===== 1. استقبال الفيديو (المصدر) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') and media.duration else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    
    db_query(
        "INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s",
        (v_id, dur, dur), fetch=False
    )
    await message.reply_text(f"✅ تم استلام الملف ({dur}).\n**أرسل البوستر الآن واكتب الاسم في وصفه.**", quote=True)

# ===== 2. استقبال البوستر (المصدر) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY created_at DESC LIMIT 1")
    if not res: return

    v_id = res[0][0]
    title = message.caption
    if not title:
        await message.reply_text("⚠️ خطأ: يجب كتابة الاسم في وصف الصورة!", quote=True)
        return

    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), 
         InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), 
         InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]
    ])
    await message.reply_text(f"📌 الاسم المعتمد: {title}\n**اختر الجودة الآن:**", reply_markup=markup, quote=True)

# ===== 3. الجودة ورقم الحلقة =====
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}\n**أرسل الآن رقم الحلقة فقط:**")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text)
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY created_at DESC LIMIT 1")
    if not res: return
    
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text
    
    safe_title = obfuscate_visual(escape(title))
    caption = f"🎬 <b>{safe_title}</b>\n\nالحلقة: [{ep_num}]\nالجودة: [{q}]\nالمدة: [{dur}]\n\nنتمنى لكم مشاهدة ممتعة."
    
    me = await client.get_me()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    try:
        # استخدام int() للتأكد من Peer Type
        post = await client.send_photo(chat_id=int(PUBLIC_POST_CHANNEL), photo=p_id, caption=caption, reply_markup=markup)
        db_query("UPDATE videos SET ep_num=%s, status='posted', post_id=%s WHERE v_id=%s", (ep_num, post.id, v_id), fetch=False)
        await message.reply_text(f"🚀 تم النشر بنجاح: {title}", quote=True)
    except Exception as e:
        logger.error(f"❌ Publish Error: {e}")

# ===== 4. التعديل التلقائي من المصدر =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def handle_edit(client, message):
    new_title = message.caption
    if not new_title: return
    
    res = db_query("SELECT v_id, ep_num, quality, duration, post_id FROM videos WHERE poster_id=%s LIMIT 1", (message.photo.file_id,))
    if res and res[0][4]:
        v_id, ep, q, dur, post_id = res[0]
        db_query("UPDATE videos SET title=%s WHERE v_id=%s", (new_title, v_id), fetch=False)
        
        safe_title = obfuscate_visual(escape(new_title))
        new_caption = f"🎬 <b>{safe_title}</b>\n\nالحلقة: [{ep}]\nالجودة: [{q}]\nالمدة: [{dur}]\n\nنتمنى لكم مشاهدة ممتعة."
        
        me = await client.get_me()
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
        
        try:
            await client.edit_message_caption(chat_id=int(PUBLIC_POST_CHANNEL), message_id=int(post_id), caption=new_caption, reply_markup=markup)
        except: pass

# ===== 5. البحث في الخاص =====
@app.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def search_handler(client, message):
    query = clean_for_search(message.text)
    if len(query) < 2: return

    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if query in clean_for_search(t[0])]

    if matches:
        btns = [[InlineKeyboardButton(f"🎬 {m}", callback_data=f"lst_{m[:40]}")] for m in matches[:10]]
        await message.reply_text(f"🔍 نتائج البحث:", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await message.reply_text("❌ لم يتم العثور على نتائج.")

@app.on_callback_query(filters.regex("^lst_"))
async def list_eps(client, cb):
    title = cb.data.replace("lst_", "")
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (f"{title}%",))
    btns, row = [], []
    for vid, ep in (res or []):
        row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"snd_{vid}"))
        if len(row) == 3: btns.append(row); row = []
    if row: btns.append(row)
    await cb.message.edit_text(f"📺 حلقات {title}:", reply_markup=InlineKeyboardMarkup(btns))

@app.on_callback_query(filters.regex("^snd_"))
async def send_vid(client, cb):
    v_id = cb.data.replace("snd_", "")
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        t, e, q, d = res[0]
        cap = f"<b>📺 المسلسل: {obfuscate_visual(t)}</b>\n<b>🎞️ الحلقة: {e}</b>\n<b>💿 الجودة: {q}</b>\n<b>⏳ المدة: {d}</b>"
        # التأكد من استخدام int(SOURCE_CHANNEL)
        await client.copy_message(cb.message.chat.id, int(SOURCE_CHANNEL), int(v_id), caption=cap)

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res:
            t, e, q, d = res[0]
            cap = f"<b>📺 المسلسل: {obfuscate_visual(t)}</b>\n<b>🎞️ الحلقة: {e}</b>\n<b>💿 الجودة: {q}</b>\n<b>⏳ المدة: {d}</b>"
            await client.copy_message(message.chat.id, int(SOURCE_CHANNEL), int(v_id), caption=cap)
    else:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}!", 
                               reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔍 كيف أبحث؟")]], resize_keyboard=True))

# ===== التشغيل النهائي =====
if __name__ == "__main__":
    init_database()
    app.run()
