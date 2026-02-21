import logging
import psycopg2
import os
import glob
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# الإعدادات الأساسية (تأكد من صحتها)
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

ADMIN_CHANNEL = -1003547072209 
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]
SUB_CHANNEL = "@MoAlmohsen" 

# --- دالة تشفير النص (لحماية القناة من الفلترة) ---
def encrypt_text(text):
    if not text: return "‌"
    # وضع فاصل مخفي بين كل حرف لكسر التعرف الآلي
    return "‌".join(list(text))

app = Client("mo_pro_vFinal", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=20)

# ==============================
# نظام قاعدة البيانات
# ==============================
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None)
        if commit: conn.commit()
        cur.close()
        return result
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

def init_db():
    db_query("""CREATE TABLE IF NOT EXISTS episodes (
        v_id TEXT PRIMARY KEY, poster_id TEXT, poster_uid TEXT, title TEXT, 
        ep_num INTEGER, duration TEXT, quality TEXT, views INTEGER DEFAULT 0)""", commit=True)
    db_query("""CREATE TABLE IF NOT EXISTS temp_upload (
        chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, poster_uid TEXT,
        title TEXT, ep_num INTEGER, duration TEXT, step TEXT)""", commit=True)

# ==============================
# نظام الرفع (للمشرف) - يدعم التشفير
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    if message.document and "video" not in (message.document.mime_type or ""): return
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"), commit=True)
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن واكتب العنوان في الوصف")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return
    
    f_id = message.photo.file_id if message.photo else message.document.file_id
    f_uid = message.photo.file_unique_id if message.photo else message.document.file_unique_id
    
    # تشفير العنوان فوراً عند الاستلام
    secure_title = encrypt_text(message.caption or "مسلسل")
    
    db_query("UPDATE temp_upload SET poster_id=%s, poster_uid=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", (f_id, f_uid, secure_title, message.chat.id), commit=True)
    await message.reply_text(f"📝 العنوان المشفر: `{secure_title}`\n🔢 أرسل رقم الحلقة")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep" or not message.text.isdigit(): return
    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s", (int(message.text), message.chat.id), commit=True)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p", callback_data="q_1080p"), InlineKeyboardButton("720p", callback_data="q_720p")],[InlineKeyboardButton("480p", callback_data="q_480p")]])
    await message.reply_text("🎬 اختر الجودة:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    db_query("""INSERT INTO episodes (v_id, poster_id, poster_uid, title, ep_num, duration, quality) 
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE 
                SET poster_id=EXCLUDED.poster_id, poster_uid=EXCLUDED.poster_uid, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality""", 
                (data['v_id'], data['poster_id'], data['poster_uid'], data['title'], data['ep_num'], data['duration'], quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    
    link = f"https://t.me/{(await client.get_me()).username}?start={data['v_id']}"
    cap = f"🎬 **{data['title']}**\n🔢 الحلقة: {data['ep_num']}\n⏱ المدة: {data['duration']}"
    for ch in PUBLIC_CHANNELS:
        try: await client.send_photo(ch, photo=data['poster_id'], caption=cap, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text(f"✅ تم النشر بنجاح.")

# --- ميزة تعديل العناوين القديمة وتشفيرها ---
@app.on_edited_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def on_edit_poster(client, message):
    f_uid = message.photo.file_unique_id if message.photo else message.document.file_unique_id if message.document else None
    if f_uid:
        new_title = encrypt_text(message.caption or "مسلسل")
        db_query("UPDATE episodes SET title=%s WHERE poster_uid=%s", (new_title, f_uid), commit=True)
        await message.reply_text(f"✅ تم تشفير وتحديث العنوان لجميع الحلقات المرتبطة بهذه الصورة.")

# ==============================
# نظام العرض والربط التلقائي (للأعضاء)
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    param = message.command[1] if len(message.command) > 1 else ""
    if not param: return await message.reply_text(f"أهلاً بك يا محمد في بوت السينما 🎬")

    try: await client.get_chat_member(SUB_CHANNEL, user_id)
    except:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{SUB_CHANNEL.replace('@','')}")], 
                                    [InlineKeyboardButton("🔄 تحقق", url=f"https://t.me/{(await client.get_me()).username}?start={param}")]])
        return await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=btn)

    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
    if data:
        # الربط التلقائي بالبصمة (poster_uid)
        related_eps = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_uid=%s ORDER BY ep_num ASC", (data['poster_uid'],), fetchall=True)
        buttons, row = [], []
        for ep in related_eps:
            text = f"🔹 {ep['ep_num']}" if str(ep['v_id']) == param else str(ep['ep_num'])
            row.append(InlineKeyboardButton(text, url=f"https://t.me/{(await client.get_me()).username}?start={ep['v_id']}"))
            if len(row) == 5: buttons.append(row); row = []
        if row: buttons.append(row)

        cap = f"🎬 **{data['title']} - حلقة {data['ep_num']}**\n⚙️ الجودة: {data['quality']}\n\n📌 **باقي الحلقات:**"
        try:
            await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(param), caption=cap, reply_markup=InlineKeyboardMarkup(buttons), protect_content=True)
            db_query("UPDATE episodes SET views = views + 1 WHERE v_id = %s", (param,), commit=True)
        except: await message.reply_text("❌ خطأ في جلب الحلقة.")

if __name__ == "__main__":
    init_db()
    app.run()
