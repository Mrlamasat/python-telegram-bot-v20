import os
import psycopg2
import logging
import asyncio
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==============================
# الإعدادات (استبدل القيم ببياناتك)
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

OWNER_ID = 123456789  # ضع آيدي حسابك هنا
ADMIN_CHANNEL = -1003547072209  # آيدي قناة التخزين (المصدر)
TEST_CHANNEL = "@RamadanSeries26" # يوزر قناة النشر العامة

# ==============================
# قاعدة البيانات
# ==============================
def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(query, params)
        result = None
        if fetchone: result = cur.fetchone()
        elif fetchall: result = cur.fetchall()
        if commit or not (fetchone or fetchall): conn.commit()
        cur.close()
        return result
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

def init_db():
    # جدول الحلقات الدائم
    db_query("""
        CREATE TABLE IF NOT EXISTS episodes (
            v_id TEXT PRIMARY KEY,
            poster_id TEXT,
            title TEXT,
            ep_num INTEGER,
            duration TEXT,
            quality TEXT,
            views INTEGER DEFAULT 0
        )
    """, commit=True)
    # جدول الرفع المؤقت
    db_query("""
        CREATE TABLE IF NOT EXISTS temp_upload (
            chat_id BIGINT PRIMARY KEY,
            v_id TEXT,
            poster_id TEXT,
            title TEXT,
            ep_num INTEGER,
            duration TEXT,
            step TEXT
        )
    """, commit=True)
    logger.info("Database initialized successfully.")

# ==============================
# إنشاء البوت
# ==============================
app = Client(
    "my_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=50
)

# ==============================
# مرحلة الرفع (للمطور فقط)
# ==============================

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    if message.document and "video" not in (message.document.mime_type or ""): return
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    
    db_query("""
        INSERT INTO temp_upload (chat_id, v_id, duration, step) 
        VALUES (%s, %s, %s, %s) 
        ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, duration=EXCLUDED.duration, step='awaiting_poster'
    """, (message.chat.id, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ تم استلام الفيديو\n🖼 أرسل البوستر الآن")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document | filters.sticker))
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_poster": return
    
    poster_id = message.photo.file_id if message.photo else message.sticker.file_id if message.sticker else message.document.file_id
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep_num' WHERE chat_id=%s", 
             (poster_id, message.caption or "", message.chat.id), commit=True)
    await message.reply_text("🔢 أرسل رقم الحلقة الآن")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start", "panel"]))
async def on_number(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep_num": return
    if not message.text.isdigit(): return await message.reply_text("❌ أرسل رقم فقط")
    
    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s", (int(message.text), message.chat.id), commit=True)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="q_720p"), InlineKeyboardButton("1080p", callback_data="q_1080p")]])
    await message.reply_text("✨ اختر الجودة", reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    db_query("""
        INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) 
        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET quality=EXCLUDED.quality
    """, (data['v_id'], data['poster_id'], data['title'], data['ep_num'], data['duration'], quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    
    watch_link = f"https://t.me/{(await client.get_me()).username}?start={data['v_id']}"
    caption = f"🎬 **{data['title'] if data['title'] else 'حلقة جديدة'}**\n🔢 الحلقة: {data['ep_num']}\n⏱ المدة: {data['duration']}\n✨ الجودة: {quality}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=watch_link)]])
    
    try:
        await client.send_photo(TEST_CHANNEL, photo=data['poster_id'], caption=caption, reply_markup=markup)
    except:
        await client.send_document(TEST_CHANNEL, document=data['poster_id'], caption=caption, reply_markup=markup)
    await query.message.edit_text("✅ تم النشر بنجاح")

# ==============================
# مرحلة العرض والمشاهدة
# ==============================

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) <= 1: return await message.reply_text("أهلاً بك في بوت السينما 🎬")
    v_id = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
    if not data: return await message.reply_text("❌ الحلقة غير موجودة.")

    caption = f"🎬 **{data['title'] if data['title'] else 'حلقة جديدة'}**\n\n🔢 **الحلقة:** {data['ep_num']}\n⏱ **المدة:** {data['duration']}\n✨ **الجودة:** {data['quality']}\n\nاضغط أدناه للمشاهدة 👇"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", callback_data=f"watch_{v_id}")]])
    try:
        await client.send_photo(message.chat.id, photo=data['poster_id'], caption=caption, reply_markup=markup)
    except:
        await client.send_document(message.chat.id, document=data['poster_id'], caption=caption, reply_markup=markup)

@app.on_callback_query(filters.regex(r"^watch_"))
async def play_video(client, query):
    v_id = query.data.split("_")[1]
    try:
        await query.message.delete()
        await client.copy_message(chat_id=query.message.chat.id, from_chat_id=ADMIN_CHANNEL, message_id=int(v_id), protect_content=True)
        db_query("UPDATE episodes SET views = views + 1 WHERE v_id=%s", (v_id,), commit=True)
    except:
        await query.answer("❌ الفيديو غير متوفر.", show_alert=True)

# ==============================
# لوحة التحكم (Admin Panel)
# ==============================

@app.on_message(filters.command("panel") & filters.private)
async def admin_panel(client, message):
    if message.from_user.id != OWNER_ID: return
    total_eps = db_query("SELECT COUNT(*) FROM episodes", fetchone=True)['count']
    total_views = db_query("SELECT COALESCE(SUM(views),0) as total FROM episodes", fetchone=True)['total']
    text = f"📊 **إحصائيات البوت**\n\n🎬 الحلقات: {total_eps}\n👁 المشاهدات: {total_views}"
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحديث", callback_data="refresh_panel")]]))

@app.on_callback_query(filters.regex("^refresh_panel$"))
async def refresh_p(client, query):
    if query.from_user.id == OWNER_ID:
        total_eps = db_query("SELECT COUNT(*) FROM episodes", fetchone=True)['count']
        total_views = db_query("SELECT COALESCE(SUM(views),0) as total FROM episodes", fetchone=True)['total']
        await query.message.edit_text(f"📊 **إحصائيات البوت**\n\n🎬 الحلقات: {total_eps}\n👁 المشاهدات: {total_views}", 
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحديث", callback_data="refresh_panel")]]))
    await query.answer("تم التحديث")

# ==============================
# التشغيل
# ==============================
if __name__ == "__main__":
    init_db()
    logger.info("Bot is Live!")
    app.run()
