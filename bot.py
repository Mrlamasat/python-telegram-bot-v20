import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

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

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)

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
# دالة إرسال الفيديو
# ==============================
async def send_video_file(client, chat_id, v_id_str):
    try:
        await client.copy_message(chat_id, ADMIN_CHANNEL, int(v_id_str), protect_content=True)
        check = db_query("SELECT v_id FROM episodes WHERE v_id=%s", (v_id_str,), fetchone=True)
        if check:
            db_query("UPDATE episodes SET views = views + 1 WHERE v_id=%s", (v_id_str,), commit=True)
        else:
            db_query("INSERT INTO episodes (v_id, title, ep_num, duration, quality, views) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (v_id_str, "حلقة من الأرشيف", 0, "00:00", "HD", 1), commit=True)
    except Exception as e:
        logger.error(f"Error sending video {v_id_str}: {e}")
        await client.send_message(chat_id, "❌ عذراً، الحلقة غير متوفرة في التخزين.")

# ==============================
# نظام الرفع (للأدمن)
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
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", (p_id, (message.caption or "بدون عنوان"), message.chat.id), commit=True)
    await message.reply_text("🔢 أرسل رقم الحلقة")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start"]))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep" or not message.text.isdigit(): return
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id, title=EXCLUDED.title, ep_num=EXCLUDED.ep_num", (data['v_id'], data['poster_id'], data['title'], int(message.text), data['duration'], "HD"), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (message.chat.id,), commit=True)
    link = f"https://t.me/{(await client.get_me()).username}?start={data['v_id']}"
    await client.send_photo(TEST_CHANNEL, photo=data['poster_id'], caption=f"🎬 **{data['title']}**\n🔢 الحلقة: {message.text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=link)]]))
    await message.reply_text("✅ تم النشر")

# ==============================
# نظام العرض والاشتراك
# ==============================
async def check_sub(client, user_id):
    try:
        await client.get_chat_member(SUB_CHANNEL, user_id)
        return True
    except UserNotParticipant: return False
    except: return True

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    param = message.command[1] if len(message.command) > 1 else ""
    
    if not await check_sub(client, user_id):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{SUB_CHANNEL.replace('@','')}")], [InlineKeyboardButton("🔄 تحقق", url=f"https://t.me/{(await client.get_me()).username}?start={param}")]])
        return await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=btn)
    
    if not param: return await message.reply_text("أهلاً بك في بوت السينما 🎬")
    if not param.isdigit(): return await message.reply_text("❌ رابط غير صالح.")

    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
    
    # تحسين: إذا فشل إرسال البوستر لأي سبب، نرسل الفيديو مباشرة
    if data and data.get('poster_id'):
        try:
            related = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=%s ORDER BY ep_num ASC", (data['poster_id'],), fetchall=True)
            keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", callback_data=f"watch_{param}")]]
            if related and len(related) > 1:
                keyboard.append([InlineKeyboardButton("🎞 حلقات أخرى 🎞", callback_data="none")])
                row = []
                for ep in related:
                    row.append(InlineKeyboardButton(f"ح {ep['ep_num']}", url=f"https://t.me/{(await client.get_me()).username}?start={ep['v_id']}"))
                    if len(row) == 4: keyboard.append(row); row = []
                if row: keyboard.append(row)
            
            cap = f"🎬 **{data.get('title', 'بدون عنوان')}**\n🔢 الحلقة: {data.get('ep_num', 0)}\n👁 المشاهدات: {data.get('views', 0)}"
            await message.reply_photo(photo=data['poster_id'], caption=cap, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Poster failed: {e}")
            await send_video_file(client, message.chat.id, param)
    else:
        await send_video_file(client, message.chat.id, param)

@app.on_callback_query(filters.regex(r"^watch_"))
async def play(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    await send_video_file(client, query.message.chat.id, v_id)

if __name__ == "__main__":
    init_db()
    app.run()
