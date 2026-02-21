import logging
import psycopg2
import os
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# الإعدادات
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@RamadanSeries26"
SUB_CHANNEL = "@MoAlmohsen"
INVITE_LINK = "https://t.me/+bU0La1OJyXowNDg0"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)

# ==============================
# قاعدة البيانات
# ==============================
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
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
    db_query("""CREATE TABLE IF NOT EXISTS episodes (
        v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT, 
        ep_num INTEGER, duration TEXT, quality TEXT, views INTEGER DEFAULT 0)""", commit=True)
    db_query("ALTER TABLE episodes ADD COLUMN IF NOT EXISTS views INTEGER DEFAULT 0", commit=True)

# ==============================
# نظام الرفع (للأدمن)
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    sec = message.video.duration if message.video else 0
    dur = f"{sec//60}:{sec%60:02d}"
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", (message.chat.id, v_id, dur), commit=True)
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def on_poster(client, message):
    p_id = message.photo.file_id if message.photo else message.document.file_id
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", (p_id, (message.caption or "حلقة جديدة"), message.chat.id), commit=True)
    await message.reply_text("🔢 أرسل رقم الحلقة")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_num(client, message):
    if not message.text.isdigit(): return
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not data: return
    db_query("""INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) 
                VALUES (%s, %s, %s, %s, %s, '720p') ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id""", 
                (data['v_id'], data['poster_id'], data['title'], int(message.text), data['duration']), commit=True)
    link = f"https://t.me/{(await client.get_me()).username}?start={data['v_id']}"
    await client.send_photo(TEST_CHANNEL, photo=data['poster_id'], caption=f"🎬 **{data['title']}**\n🔢 الحلقة: {message.text}\n⏱ المدة: {data['duration']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=link)]]))
    await message.reply_text("✅ تم النشر")

# ==============================
# نظام العرض
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    param = message.command[1] if len(message.command) > 1 else ""
    if not param: return await message.reply_text("أهلاً بك يا محمد 🎬")
    
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
    if data:
        cap = f"🎬 **{data['title']}**\n\n🔢 الحلقة: {data['ep_num']}\n⏱ المدة: {data['duration']}\n👁 المشاهدات: {data['views']}"
        await message.reply_photo(photo=data['poster_id'], caption=cap, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", callback_data=f"watch_{param}")]]))
    else:
        await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(param))

@app.on_callback_query(filters.regex(r"^watch_"))
async def play(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await client.copy_message(query.message.chat.id, ADMIN_CHANNEL, int(v_id))
    db_query("UPDATE episodes SET views = views + 1 WHERE v_id = %s", (v_id,), commit=True)

# ==============================
# التشغيل المستقر
# ==============================
if __name__ == "__main__":
    if os.path.exists("my_bot.session"):
        try: os.remove("my_bot.session")
        except: pass
    init_db()
    logger.info("🚀 جاري التشغيل...")
    app.run()
