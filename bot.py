import os
import psycopg2
import psycopg2.pool
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الثابتة =====
API_ID = int(os.environ.get("API_ID", "24803515"))
API_HASH = os.environ.get("API_HASH", "86414909a34199f18742f1b490f892cc")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHrgUVKh0D45SMa0iHYI-DkbuWxeYm-rns")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway")

# المعرفات التي زودتني بها
SOURCE_CHANNEL = -1003547072209
TARGET_CHANNEL = -1003554018307
FORCE_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0" # رابط القناة الثالثة

app = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode="require")

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = db_pool.getconn()
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch: result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: db_pool.putconn(conn)

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            status TEXT DEFAULT 'waiting'
        )
    """, fetch=False)

# ===== معالج الرفع والأرشفة الذكي =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id,), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو (ID: {v_id}).\nالآن أرسل **البوستر** كصورة مع اسم المسلسل في الوصف.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def on_photo(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل غير معروف"
    
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='posted' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    # النشر في القناة النهائية
    me = await client.get_me()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    try:
        await client.send_photo(chat_id=TARGET_CHANNEL, photo=message.photo.file_id, caption=f"🎬 **{title}**\n\nاضغط للمشاهدة 👇", reply_markup=markup)
        await message.reply_text("🚀 تم النشر بنجاح في قناة الأعضاء.")
    except Exception as e:
        await message.reply_text(f"❌ فشل النشر. تأكد أن البوت مشرف في القناة {TARGET_CHANNEL}\nالخطأ: {e}")

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد! أرسل الفيديو في القناة المصدر للبدء.")

    v_id = message.command[1]
    
    # فحص الاشتراك الإجباري
    try:
        user = await client.get_chat_member(FORCE_CHANNEL, message.from_user.id)
        if user.status in ["left", "kicked"]: raise Exception()
    except:
        return await message.reply_text("❌ اشترك في القناة أولاً للمشاهدة:\n" + FORCE_SUB_LINK)

    # جلب ذكي من المصدر (حتى لو القاعدة محذوفة)
    try:
        await client.copy_message(chat_id=message.chat.id, from_chat_id=SOURCE_CHANNEL, message_id=int(v_id), caption="🍿 مشاهدة ممتعة!")
    except:
        await message.reply_text("❌ هذه الحلقة قديمة جداً ولم تعد موجودة في الأرشيف.")

if __name__ == "__main__":
    init_db()
    app.run()
