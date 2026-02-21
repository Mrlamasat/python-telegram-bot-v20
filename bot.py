import os
import psycopg2
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# المتغيرات
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_CHANNEL = -1003547072209 

app = Client("CinemaBot_AutoReg", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- إدارة قاعدة البيانات ---
def db_query(query, params=(), fetchone=False, commit=False):
    conn = None
    res = None
    try:
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url, sslmode='require')
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetchone: res = cursor.fetchone()
        if commit: conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"❌ DB Error: {e}")
    finally:
        if conn: conn.close()
    return res

def init_db():
    db_query('CREATE TABLE IF NOT EXISTS episodes (v_id TEXT PRIMARY KEY, poster_id TEXT, title TEXT)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS temp_upload (chat_id BIGINT PRIMARY KEY, v_id TEXT, step TEXT)', commit=True)

# --- نظام التشغيل والتسجيل التلقائي ---
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # 1. البحث في القاعدة أولاً
        ep = db_query("SELECT poster_id, title FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
        
        if ep:
            # إذا كانت موجودة، نرسل البوستر ثم الفيديو
            if ep[0] != "auto":
                await client.send_photo(message.chat.id, photo=ep[0], caption=f"🎬 **{ep[1]}**")
            await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
        else:
            # 2. "التسجيل التلقائي": إذا لم تكن موجودة، نجلبها من القناة ونسجلها
            try:
                # محاولة جلب الرسالة من قناة الإدارة للتأكد من وجودها
                msg = await client.get_messages(ADMIN_CHANNEL, int(v_id))
                if msg:
                    # إرسال الفيديو للزائر فوراً
                    await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(v_id), protect_content=True)
                    
                    # تسجيلها في القاعدة لكي لا يضطر البوت للبحث عنها مجدداً
                    db_query("INSERT INTO episodes (v_id, poster_id, title) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
                             (v_id, "auto", "حلقة مسجلة تلقائياً"), commit=True)
                    logger.info(f"✅ تم تسجيل الحلقة {v_id} تلقائياً")
            except Exception as e:
                await message.reply_text("❌ عذراً، هذه الحلقة غير متوفرة في الأرشيف.")
    else:
        await message.reply_text("أهلاً بك يا محمد! أرسل رابط الحلقة لمشاهدتها.")

# --- نظام الرفع اليدوي (مع حل مشكلة الصورة) ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO temp_upload (chat_id, v_id, step) VALUES (%s, %s, 'wait_poster') ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='wait_poster'", (ADMIN_CHANNEL, v_id), commit=True)
    await message.reply_text(f"✅ استلمت الفيديو ({v_id})\n🖼 أرسل البوستر الآن كصورة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.photo)
async def on_poster(client, message):
    res = db_query("SELECT v_id FROM temp_upload WHERE chat_id=%s AND step='wait_poster'", (ADMIN_CHANNEL,), fetchone=True)
    if not res: return
    
    v_id = res[0]
    db_query("INSERT INTO episodes (v_id, poster_id, title) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET poster_id=EXCLUDED.poster_id, title=EXCLUDED.title", (v_id, message.photo.file_id, message.caption or "بدون عنوان"), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)
    
    await message.reply_text(f"🚀 تم حفظ الحلقة بنجاح!\n🔗 الرابط: `https://t.me/{(await client.get_me()).username}?start={v_id}`")

if __name__ == "__main__":
    init_db()
    app.run()
