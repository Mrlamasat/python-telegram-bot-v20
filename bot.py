import os
import psycopg2
import logging
import base64
import threading
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from fastapi import FastAPI
import uvicorn

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
api = FastAPI()

# ===== [2] قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

def init_database():
    db_query("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, joined_at TIMESTAMP DEFAULT NOW())", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS views_log (v_id TEXT, viewed_at TIMESTAMP DEFAULT NOW())", fetch=False)
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, title TEXT, poster_id TEXT, 
            ep_num INTEGER, status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0, last_view TIMESTAMP
        )
    """, fetch=False)

# ===== [3] عرض الحلقة =====
async def show_episode(client, message, v_id):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not res: return
    
    title, ep = res[0]
    db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (v_id,), fetch=False)

    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 اضغط هنا للاشتراك بالقناه الإحتياطيه", url=BACKUP_CHANNEL_LINK)]])
    
    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)

# ===== [4] نظام الـ API للموقع (الجسر) =====
@api.get("/api/episodes")
def get_episodes_for_web():
    # جلب آخر 24 حلقة تم نشرها لعرضها في الموقع
    rows = db_query("SELECT v_id, title, ep_num FROM videos WHERE status='posted' ORDER BY v_id DESC LIMIT 24")
    data = []
    for r in rows:
        data.append({
            "id": base64.b64encode(str(r[0]).encode()).decode(), # تشفير الـ ID لحماية القناة
            "title": r[1],
            "episode": r[2]
        })
    return data

# ===== [5] الأوامر والنشر =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        try:
            # محاولة فك تشفير المعرف القادم من الموقع
            v_id = base64.b64decode(message.command[1]).decode()
            await show_episode(client, message, v_id)
        except:
            await show_episode(client, message, message.command[1])
    else:
        await message.reply_text(f"👋 أهلاً بك يا محمد.\nالبوت متصل الآن بالموقع الإلكتروني.")

@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
        await message.reply_text(f"✅ تم استلام الفيديو `{message.id}`")
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption, message.photo.file_id, res[0][0]), fetch=False)
            await message.reply_text(f"🖼️ تم حفظ البوستر لـ: {message.caption}")
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]; ep_num = int(message.text)
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
            me = await client.get_me()
            # الرابط هنا مشفر لحماية القناة
            encoded_id = base64.b64encode(str(v_id).encode()).decode()
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ شاهد الآن في الموقع", url=f"https://t.me/{me.username}?start={encoded_id}")]])
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep_num}]</b>", reply_markup=markup)
            await message.reply_text(f"🚀 تم النشر بنجاح!")

# دالة تشغيل الجسر
def run_api():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(api, host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_database()
    # تشغيل الجسر والبوت معاً
    threading.Thread(target=run_api, daemon=True).start()
    app.run()
