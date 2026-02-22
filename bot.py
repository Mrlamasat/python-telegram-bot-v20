import logging
import psycopg2
import os
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import asyncio

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
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]
SUB_CHANNEL = "@MoAlmohsen" 

app = Client("mo_pro_vFixed", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=20)

def encrypt_text(text):
    return "‌".join(list(text)) if text else "‌"

# ==============================
# قاعدة البيانات
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
    try:
        db_query("ALTER TABLE episodes ADD COLUMN IF NOT EXISTS poster_uid TEXT", commit=True)
    except: pass

# ==============================
# نظام الرفع (للمشرف)
# ==============================

# الخطوة 1: استلام الفيديو
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"), commit=True)
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن واكتب العنوان في الوصف (Caption)")

# الخطوة 2: استلام البوستر (هنا كان الخطأ وتم إصلاحه)
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return
    
    f_id = message.photo.file_id if message.photo else message.document.file_id
    f_uid = message.photo.file_unique_id if message.photo else message.document.file_unique_id
    secure_title = encrypt_text(message.caption or "مسلسل")
    
    # تحديث الحالة إلى awaiting_ep لكي ينتقل لرقم الحلقة
    db_query("UPDATE temp_upload SET poster_id=%s, poster_uid=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", (f_id, f_uid, secure_title, message.chat.id), commit=True)
    await message.reply_text(f"✅ تم حفظ البوستر لـ: {secure_title}\n🔢 الآن أرسل **رقم الحلقة** فقط:")

# الخطوة 3: استلام رقم الحلقة
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep": return
    
    if not message.text.isdigit():
        return await message.reply_text("⚠️ يرجى إرسال رقم صحيح (أرقام فقط)")

    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s", (int(message.text), message.chat.id), commit=True)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p", callback_data="q_1080p"), InlineKeyboardButton("720p", callback_data="q_720p")]])
    await message.reply_text(f"🎬 الحلقة {message.text}.. اختر الجودة للنشر:", reply_markup=kb)

# الخطوة 4: اختيار الجودة والنشر النهائي
@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    db_query("""INSERT INTO episodes (v_id, poster_id, poster_uid, title, ep_num, duration, quality) 
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE 
                SET poster_id=EXCLUDED.poster_id, poster_uid=EXCLUDED.poster_uid, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality, title=EXCLUDED.title""", 
                (data['v_id'], data['poster_id'], data['poster_uid'], data['title'], data['ep_num'], data['duration'], quality), commit=True)
    
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['v_id']}"
    
    for ch in PUBLIC_CHANNELS:
        try:
            await client.send_photo(ch, photo=data['poster_id'], caption=f"🎬 **{data['title']}**\n🔢 الحلقة: {data['ep_num']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except: pass
        
    await query.message.edit_text(f"✅ تم النشر بنجاح في القنوات.")

# ==============================
# نظام التشغيل (الأعضاء)
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    param = message.command[1] if len(message.command) > 1 else ""
    if not param: return await message.reply_text(f"أهلاً بك يا محمد 🎬")

    try: await client.get_chat_member(SUB_CHANNEL, user_id)
    except:
        bot_info = await client.get_me()
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{SUB_CHANNEL.replace('@','')}")], 
                                    [InlineKeyboardButton("🔄 تحقق", url=f"https://t.me/{bot_info.username}?start={param}")]])
        return await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=btn)

    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
    if data:
        buttons = []
        if data.get('poster_uid'):
            related = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_uid=%s ORDER BY ep_num ASC", (data['poster_uid'],), fetchall=True)
            bot_info = await client.get_me()
            row = []
            for ep in related:
                clean_id = str(ep['v_id']).strip()
                label = f"🔹 {ep['ep_num']}" if clean_id == param else str(ep['ep_num'])
                row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={clean_id}"))
                if len(row) == 5: buttons.append(row); row = []
            if row: buttons.append(row)

        cap = f"🎬 **{data['title']} - حلقة {data['ep_num']}**\n⚙️ الجودة: {data['quality']}"
        try:
            peer = int(ADMIN_CHANNEL) if str(ADMIN_CHANNEL).replace("-", "").isdigit() else ADMIN_CHANNEL
            await client.copy_message(chat_id=message.chat.id, from_chat_id=peer, message_id=int(data['v_id']), caption=cap, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None, protect_content=True)
            db_query("UPDATE episodes SET views = views + 1 WHERE v_id = %s", (param,), commit=True)
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
    else:
        await message.reply_text("❌ الحلقة غير موجودة.")

if __name__ == "__main__":
    init_db()
    app.run()
