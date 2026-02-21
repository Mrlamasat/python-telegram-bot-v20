import os
import psycopg2
import logging
import asyncio
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserNotParticipant

# ==============================
# الإعدادات
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

OWNER_ID = 123456789  # ضع آيدي حسابك هنا
ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@RamadanSeries26" # قناة النشر العامة
SUB_CHANNEL = "@MoAlmohsen"      # قناة الاشتراك الإجباري الجديدة

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

# ==============================
# دالة التحقق من الاشتراك
# ==============================
async def check_sub(client, user_id):
    try:
        await client.get_chat_member(SUB_CHANNEL, user_id)
        return True
    except UserNotParticipant:
        return False
    except Exception:
        return True 

# ==============================
# إنشاء البوت
# ==============================
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)

# ==============================
# مرحلة الرفع
# ==============================

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    if message.document and "video" not in (message.document.mime_type or ""): return
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", (message.chat.id, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document | filters.sticker))
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_poster": return
    p_id = message.photo.file_id if message.photo else message.document.file_id
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", (p_id, message.caption or "", message.chat.id), commit=True)
    await message.reply_text("🔢 أرسل رقم الحلقة")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start", "panel"]))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep": return
    if not message.text.isdigit(): return
    db_query("UPDATE temp_upload SET ep_num=%s, step='done' WHERE chat_id=%s", (int(message.text), message.chat.id), commit=True)
    
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s)", (data['v_id'], data['poster_id'], data['title'], data['ep_num'], data['duration'], "HD"), commit=True)
    
    link = f"https://t.me/{(await client.get_me()).username}?start={data['v_id']}"
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=link)]])
    await client.send_photo(TEST_CHANNEL, photo=data['poster_id'], caption=f"🎬 **{data['title']}**\n🔢 الحلقة: {data['ep_num']}", reply_markup=btn)
    await message.reply_text("✅ تم النشر")

# ==============================
# العرض والمشاهدة + المزيد من الحلقات
# ==============================

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    # تحقق من الاشتراك الإجباري في القناة الجديدة
    if not await check_sub(client, message.from_user.id):
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{SUB_CHANNEL.replace('@','')}")],
            [InlineKeyboardButton("🔄 تحقق من الاشتراك", url=f"https://t.me/{(await client.get_me()).username}?start={message.command[1] if len(message.command)>1 else ''}")]
        ])
        return await message.reply_text(f"⚠️ عذراً يا {message.from_user.first_name}، يجب عليك الاشتراك في القناة أولاً لمشاهدة الحلقات.", reply_markup=btn)

    if len(message.command) <= 1: return await message.reply_text("أهلاً بك في بوت السينما 🎬")
    
    v_id = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
    
    if data:
        # نظام "المزيد من الحلقات" من نفس المسلسل
        others = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=%s AND v_id!=%s ORDER BY ep_num ASC", (data['poster_id'], v_id), fetchall=True)
        
        keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", callback_data=f"watch_{v_id}")]]
        
        if others:
            keyboard.append([InlineKeyboardButton("🎞 المزيد من الحلقات 🎞", callback_data="none")])
            row = []
            for ep in others:
                row.append(InlineKeyboardButton(f"ح {ep['ep_num']}", url=f"https://t.me/{(await client.get_me()).username}?start={ep['v_id']}"))
                if len(row) == 4:
                    keyboard.append(row)
                    row = []
            if row: keyboard.append(row)

        caption = f"🎬 **{data['title']}**\n\n🔢 **الحلقة:** {data['ep_num']}\n⏱ **المدة:** {data['duration']}\n👁 المشاهدات: {data['views']}"
        try:
            await client.send_photo(message.chat.id, photo=data['poster_id'], caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # الجلب التلقائي للحلقات القديمة
        try:
            await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
            # تسجيلها تلقائياً لتظهر بالبوستر مستقبلاً
            db_query("INSERT INTO episodes (v_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (v_id, "حلقة مستعادة", 0, "00:00", "HD"), commit=True)
        except:
            await message.reply_text("❌ غير موجود.")

@app.on_callback_query(filters.regex(r"^watch_"))
async def play(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await client.copy_message(query.message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
    db_query("UPDATE episodes SET views = views + 1 WHERE v_id=%s", (v_id,), commit=True)

if __name__ == "__main__":
    init_db()
    app.run()
