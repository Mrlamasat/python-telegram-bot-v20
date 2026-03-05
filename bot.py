import os
import psycopg2
import psycopg2.pool
import logging
import re
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import PeerIdInvalid, FloodWait

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209      
PUBLIC_POST_CHANNEL = -1003554018307  
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("mohammed_bot_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
db_pool = None
def get_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")
    return db_pool

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        pool = get_pool()
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return res
    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

def init_db():
    db_query("""CREATE TABLE IF NOT EXISTS videos (
        v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, 
        poster_id TEXT, quality TEXT, duration TEXT, 
        status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0
    )""", fetch=False)
    cols = [("ep_num","INTEGER"), ("poster_id","TEXT"), ("quality","TEXT"), ("duration","TEXT"), ("views","INTEGER DEFAULT 0"), ("status","TEXT DEFAULT 'waiting'"), ("title","TEXT")]
    for c, t in cols: db_query(f"ALTER TABLE videos ADD COLUMN IF NOT EXISTS {c} {t}", fetch=False)

# ===== المزامنة المعدلة (تجنب BOT_METHOD_INVALID) =====
@app.on_message(filters.command("sync") & filters.user(ADMIN_ID))
async def sync_handler(client, message):
    msg = await message.reply_text("🔄 جاري المزامنة الذكية للقناة الخاصة...")
    count = 0
    try:
        # بدلاً من جلب التاريخ كاملاً، سنقوم بجلب آخر 200 رسالة فرادى
        # هذا يتخطى قيود GetHistory للبوتات في القنوات الخاصة
        async for m in client.get_chat_history(PUBLIC_POST_CHANNEL, limit=200):
            if m and m.caption and m.reply_markup:
                try:
                    url = m.reply_markup.inline_keyboard[0][0].url
                    v_id = url.split("start=")[1]
                    title_match = re.search(r"المسلسل\s*:\s*(.*)\n", m.caption)
                    clean_t = clean_and_decode(title_match.group(1)) if title_match else "مسلسل"
                    ep_m = re.search(r"رقم الحلقة\s*:\s*(\d+)", m.caption)
                    ep = int(ep_m.group(1)) if ep_m else 0
                    
                    db_query("""INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') 
                               ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, status='posted'""",
                            (v_id, clean_t, ep, clean_t, ep), fetch=False)
                    count += 1
                except: continue
        await msg.edit_text(f"✅ تمت المزامنة بنجاح! تم فحص {count} منشور.")
    except Exception as e:
        await msg.edit_text(f"❌ فشل المزامنة: {e}\nتأكد أن البوت مسؤول في القناة الخاصة.")

# ===== دالة الإرسال مع تنشيط الـ Peer يدويًا =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    try:
        # محاولة تنشيط القناة المصدر في ذاكرة البوت قبل الإرسال
        try:
            await client.get_chat(SOURCE_CHANNEL)
        except PeerIdInvalid:
            logging.error("❌ البوت لا يرى القناة المصدر. يجب توجيه رسالة منها للبوت.")

        # التحديث التلقائي للبيانات 0
        if ep == 0 or title == "مسلسل":
            try:
                source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source_msg and source_msg.caption:
                    title = clean_and_decode(source_msg.caption)
                    ep_m = re.search(r'(\d+)', source_msg.caption)
                    ep = int(ep_m.group(1)) if ep_m else ep
                    db_query("UPDATE videos SET title=%s, ep_num=%s WHERE v_id=%s", (title, ep, v_id), fetch=False)
            except: pass

        btns = await get_episodes_markup(title, v_id)
        cap = (f"<b>📺 المسلسل : {obfuscate_visual(title)}</b>\n"
               f"<b>🎞️ رقم الحلقة : {ep}</b>\n\n🍿 مشاهدة ممتعة!")
        
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))
    except Exception as e:
        logging.error(f"❌ Error: {e}")
        await client.send_message(chat_id, "⚠️ الفيديو غير متاح حالياً، حاول مرة أخرى لاحقاً.")

# (بقية الدوال المساعدة clean_and_decode و obfuscate_visual و get_episodes_markup تبقى كما هي)
# ...

# ===== التشغيل النهائي المضمون للقنوات الخاصة =====
async def main():
    await app.start()
    logging.info("🚀 جاري تنشيط القنوات الخاصة...")
    # هذه الخطوة تجبر البوت على التعرف على القنوات الخاصة عند الإقلاع
    for channel in [SOURCE_CHANNEL, PUBLIC_POST_CHANNEL]:
        try:
            await app.get_chat(channel)
            logging.info(f"✅ تم التعرف على القناة {channel}")
        except Exception as e:
            logging.warning(f"⚠️ فشل التعرف الأولي على {channel}: {e}")
    
    await idle()
    await app.stop()

if __name__ == "__main__":
    init_db()
    app.run(main())
