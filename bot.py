import logging
import psycopg2
import os
import asyncio
import glob
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# الإعدادات الأساسية
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

ADMIN_CHANNEL = -1003547072209 
# قائمة القنوات العامة للنشر
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]
SUB_CHANNEL = "@MoAlmohsen" # قناة الاشتراك الإجباري
INVITE_LINK = "https://t.me/+bU0La1OJyXowNDg0"

app = Client("mo_almohsen_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=20)

# ==============================
# نظام قاعدة البيانات
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
    db_query("""CREATE TABLE IF NOT EXISTS temp_upload (
        chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, 
        title TEXT, ep_num INTEGER, duration TEXT, step TEXT)""", commit=True)

# ==============================
# نظام الرفع (للأدمن)
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    if message.document and "video" not in (message.document.mime_type or ""): return
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    dur_str = f"{sec // 60}:{sec % 60:02d}"
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", (message.chat.id, v_id, dur_str), commit=True)
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return

    file_id = message.photo.file_id if message.photo else (message.document.file_id if (message.document and "image" in (message.document.mime_type or "")) else None)
    if not file_id: return await message.reply_text("❌ يرجى إرسال صورة صالحة")

    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", (file_id, (message.caption or "حلقة جديدة"), message.chat.id), commit=True)
    await message.reply_text("🔢 أرسل رقم الحلقة")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep" or not message.text.isdigit(): return
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    
    # حفظ البيانات في قاعدة البيانات
    db_query("""INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality, views) 
                VALUES (%s, %s, %s, %s, %s, '720p', 0) 
                ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id, title=EXCLUDED.title, ep_num=EXCLUDED.ep_num""", 
                (data['v_id'], data['poster_id'], data['title'], int(message.text), data['duration']), commit=True)
    
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (message.chat.id,), commit=True)
    
    # إعداد رسالة النشر
    bot_username = (await client.get_me()).username
    link = f"https://t.me/{bot_username}?start={data['v_id']}"
    cap = f"🎬 **{data['title']}**\n\n🔢 الحلقة: {message.text}\n⏱ المدة: {data['duration']}"
    
    # النشر في القناتين
    for channel in PUBLIC_CHANNELS:
        try:
            await client.send_photo(
                channel, 
                photo=data['poster_id'], 
                caption=cap, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=link)]])
            )
        except Exception as e:
            logger.error(f"Error publishing to {channel}: {e}")

    await message.reply_text(f"✅ تم النشر بنجاح في القنوات: {', '.join(PUBLIC_CHANNELS)}")

# ==============================
# نظام العرض والاشتراك
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    param = message.command[1] if len(message.command) > 1 else ""
    
    # تحقق الاشتراك الإجباري
    try:
        await client.get_chat_member(SUB_CHANNEL, user_id)
    except:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{SUB_CHANNEL.replace('@','')}")], 
                                    [InlineKeyboardButton("🔄 تحقق", url=f"https://t.me/{(await client.get_me()).username}?start={param}")]])
        return await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=btn)
    
    if not param: return await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت السينما 🎬")
    
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
    
    if data:
        cap = f"🎬 **{data['title']}**\n\n🔢 الحلقة: {data['ep_num']}\n⏱ المدة: {data['duration']}\n👁 المشاهدات: {data['views']}"
        keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", callback_data=f"watch_{param}")]]
        try: await message.reply_photo(photo=data['poster_id'], caption=cap, reply_markup=InlineKeyboardMarkup(keyboard))
        except: await message.reply_text(cap, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        try: await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(param), protect_content=True)
        except: await message.reply_text("❌ عذراً، لم أجد هذه الحلقة.")

@app.on_callback_query(filters.regex(r"^watch_"))
async def play(client, query):
    v_id = query.data.split("_")[1]
    await query.message.delete()
    try:
        await client.copy_message(query.message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
        db_query("UPDATE episodes SET views = views + 1 WHERE v_id = %s", (v_id,), commit=True)
    except: await client.send_message(query.message.chat.id, "❌ فشل إرسال الفيديو.")

# ==============================
# التشغيل
# ==============================
if __name__ == "__main__":
    for f in glob.glob("*.session*"):
        try: os.remove(f)
        except: pass
    init_db()
    app.run()
