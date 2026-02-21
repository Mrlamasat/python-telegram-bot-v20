import logging
import psycopg2
import os
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# الإعدادات - غير ADMIN_CHANNEL لليوزر الجديد
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# نصيحة: استخدم يوزر القناة هنا لضمان عدم حدوث خطأ Peer ID
ADMIN_CHANNEL = -1003547072209 
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]
SUB_CHANNEL = "@MoAlmohsen" 

app = Client("mo_final_stable_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=20)

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

# ==============================
# نظام التشغيل الذكي
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    param = message.command[1] if len(message.command) > 1 else ""
    if not param: return await message.reply_text(f"أهلاً بك يا محمد 🎬")

    # فحص الاشتراك
    try:
        await client.get_chat_member(SUB_CHANNEL, user_id)
    except:
        bot_info = await client.get_me()
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{SUB_CHANNEL.replace('@','')}")], 
                                    [InlineKeyboardButton("🔄 تحقق", url=f"https://t.me/{bot_info.username}?start={param}")]])
        return await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=btn)

    # جلب الحلقة
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
    
    # محاولة الإنقاذ
    if not data:
        try:
            old_msg = await client.get_messages(ADMIN_CHANNEL, int(param))
            if old_msg:
                db_query("INSERT INTO episodes (v_id, title, ep_num, quality) VALUES (%s, %s, %s, %s)", (param, "حلقة مؤرشفة", 0, "HD"), commit=True)
                data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
        except: pass

    if data:
        buttons = []
        if data.get('poster_uid'):
            related = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_uid=%s ORDER BY ep_num ASC", (data['poster_uid'],), fetchall=True)
            bot_info = await client.get_me()
            row = []
            for ep in related:
                row.append(InlineKeyboardButton(f"🔹 {ep['ep_num']}" if str(ep['v_id']) == param else str(ep['ep_num']), url=f"https://t.me/{bot_info.username}?start={ep['v_id']}"))
                if len(row) == 5: buttons.append(row); row = []
            if row: buttons.append(row)

        try:
            # النسخ المباشر
            await client.copy_message(
                chat_id=message.chat.id, 
                from_chat_id=ADMIN_CHANNEL, 
                message_id=int(data['v_id']), 
                caption=f"🎬 **{data['title']}**", 
                reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
            )
        except Exception as e:
            await message.reply_text(f"❌ خطأ سحب الفيديو: {e}")
    else:
        await message.reply_text("❌ الحلقة غير موجودة.")

# ==============================
# دالة الرفع الأساسية
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO temp_upload (chat_id, v_id, step) VALUES (%s, %s, 'awaiting_poster') ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", (message.chat.id, v_id), commit=True)
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.photo)
async def on_poster(client, message):
    state = db_query("SELECT v_id FROM temp_upload WHERE chat_id=%s AND step='awaiting_poster'", (message.chat.id,), fetchone=True)
    if not state: return
    f_uid = message.photo.file_unique_id
    db_query("INSERT INTO episodes (v_id, poster_id, poster_uid, title, ep_num, quality) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET poster_uid=EXCLUDED.poster_uid", (state['v_id'], message.photo.file_id, f_uid, "مسلسل", 1, "HD"), commit=True)
    await message.reply_text("✅ تم الحفظ بنجاح")

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS episodes (v_id TEXT PRIMARY KEY, poster_id TEXT, poster_uid TEXT, title TEXT, ep_num INTEGER, duration TEXT, quality TEXT, views INTEGER DEFAULT 0)", commit=True)
    db_query("CREATE TABLE IF NOT EXISTS temp_upload (chat_id BIGINT PRIMARY KEY, v_id TEXT, poster_id TEXT, poster_uid TEXT, title TEXT, ep_num INTEGER, duration TEXT, step TEXT)", commit=True)
    app.run()
