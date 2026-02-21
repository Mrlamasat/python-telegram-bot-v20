import os
import psycopg2
import logging
import asyncio
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserNotParticipant

# ==============================
# الإعدادات (تأكد من صحة الآيديات)
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

OWNER_ID = 123456789  # ضع آيديك الحقيقي هنا
ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@RamadanSeries26" 
SUB_CHANNEL = "@MoAlmohsen"      

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
# التحقق من الاشتراك
# ==============================
async def check_sub(client, user_id):
    try:
        await client.get_chat_member(SUB_CHANNEL, user_id)
        return True
    except UserNotParticipant:
        return False
    except:
        return True 

# ==============================
# إنشاء البوت
# ==============================
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)

# ==============================
# نظام الرفع (الأدمن)
# ==============================

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    if message.document and "video" not in (message.document.mime_type or ""): return
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, duration=EXCLUDED.duration, step='awaiting_poster'", (message.chat.id, v_id, duration, "awaiting_poster"), commit=True)
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
    
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    db_query("INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id, title=EXCLUDED.title, ep_num=EXCLUDED.ep_num", (data['v_id'], data['poster_id'], data['title'], int(message.text), data['duration'], "HD"), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (message.chat.id,), commit=True)
    
    link = f"https://t.me/{(await client.get_me()).username}?start={data['v_id']}"
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة", url=link)]])
    await client.send_photo(TEST_CHANNEL, photo=data['poster_id'], caption=f"🎬 **{data['title']}**\n🔢 الحلقة: {message.text}", reply_markup=btn)
    await message.reply_text("✅ تم النشر بنجاح")

# ==============================
# نظام العرض (المستخدم)
# ==============================

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if not await check_sub(client, message.from_user.id):
        param = message.command[1] if len(message.command) > 1 else ""
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{SUB_CHANNEL.replace('@','')}")],
            [InlineKeyboardButton("🔄 تحقق من الاشتراك", url=f"https://t.me/{(await client.get_me()).username}?start={param}")]
        ])
        return await message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة الحلقات.", reply_markup=btn)

    if len(message.command) <= 1: return await message.reply_text("أهلاً بك في بوت السينما 🎬")
    
    v_id_str = message.command[1]
    if not v_id_str.isdigit(): return await message.reply_text("❌ رابط غير صالح.")
    
    # البحث في القاعدة
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (v_id_str,), fetchone=True)
    
    if data and data['poster_id']:
        # إذا كانت الحلقة مسجلة ببوستر
        others = db_query("SELECT v_id, ep_num FROM episodes WHERE title=%s AND v_id!=%s ORDER BY ep_num ASC", (data['title'], v_id_str), fetchall=True)
        keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", callback_data=f"watch_{v_id_str}")]]
        
        if others:
            keyboard.append([InlineKeyboardButton("🎞 حلقات أخرى للمسلسل 🎞", callback_data="none")])
            row = []
            for ep in others:
                row.append(InlineKeyboardButton(f"ح {ep['ep_num']}", url=f"https://t.me/{(await client.get_me()).username}?start={ep['v_id']}"))
                if len(row) == 4:
                    keyboard.append(row); row = []
            if row: keyboard.append(row)

        caption = f"🎬 **{data['title']}**\n\n🔢 **الحلقة:** {data['ep_num']}\n⏱ **المدة:** {data['duration']}\n👁 المشاهدات: {data['views']}"
        await client.send_photo(message.chat.id, photo=data['poster_id'], caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
    
    else:
        # الحل للمشكلة: الجلب المباشر للحلقات القديمة من قناة الأدمن
        try:
            # نحاول إرسال الفيديو مباشرة
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=ADMIN_CHANNEL,
                message_id=int(v_id_str),
                protect_content=True
            )
            # تسجيلها تلقائياً لضمان عدم ظهور الخطأ مستقبلاً
            db_query("INSERT INTO episodes (v_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (v_id_str, "حلقة من الأرشيف", 0, "00:00", "HD"), commit=True)
        except Exception as e:
            logger.error(f"Old episode error: {e}")
            await message.reply_text("❌ عذراً، هذه الحلقة غير متوفرة في قناة التخزين.")

@app.on_callback_query(filters.regex(r"^watch_"))
async def play(client, query):
    v_id = query.data.split("_")[1]
    try:
        await query.message.delete()
        await client.copy_message(query.message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
        db_query("UPDATE episodes SET views = views + 1 WHERE v_id=%s", (v_id,), commit=True)
    except:
        await query.answer("❌ فشل تشغيل الفيديو.", show_alert=True)

if __name__ == "__main__":
    init_db()
    app.run()
