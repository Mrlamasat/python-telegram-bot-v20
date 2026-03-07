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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# تصريح المرور للموقع (CORS)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# قائمة الأسماء الصحيحة التي زودتني بها لتصحيح البيانات القديمة
CORRECT_TITLES = [
    "اولاد الراعي", "كلهم بيحبو مودي", "الست موناليزا", "فن الحرب",
    "افراج", "الكاميرا الخفيه", "رامز ليفل الوحش", "صحاب الارض",
    "وننسى اللي كان", "علي كلاي", "عين سحريه", "فخر الدلتا",
    "الكينج", "درش", "راس الافعى", "المداح", "هي كيميا", "سوا سوا",
    "بيبو", "النص الثاني", "عرض وطلب", "مولانا", "فرصه اخيره",
    "حكايه نرجس", "اب ولكن", "اللون الازرق", "المتر سمير",
    "بابا وماما جيران", "قطر صغنطوط", "ن النسوه"
]

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

# دالة تنظيف البيانات القديمة وتصحيح الأسماء
def clean_old_data():
    try:
        db_query("DELETE FROM videos WHERE title LIKE '%اضغط هنا%' OR title IS NULL", fetch=False)
        current_videos = db_query("SELECT v_id, title FROM videos")
        
        for v_id, title in current_videos:
            if not title: continue
            clean_t = title.replace(" ", "").strip()
            match_found = False
            
            for correct in CORRECT_TITLES:
                if correct.replace(" ", "") in clean_t or clean_t in correct.replace(" ", ""):
                    db_query("UPDATE videos SET title=%s WHERE v_id=%s", (correct, v_id), fetch=False)
                    match_found = True
                    break
            
            if not match_found:
                # نحذف الحلقات القديمة التي ليست في القائمة ولم يتم التعرف عليها
                db_query("DELETE FROM videos WHERE v_id=%s", (v_id,), fetch=False)
        logging.info("✅ Database Cleanup Completed.")
    except Exception as e:
        logging.error(f"Cleanup Error: {e}")

# ===== [3] عرض الحلقة والـ API =====
async def show_episode(client, message, v_id):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (str(v_id),))
    if not res: 
        await message.reply_text("❌ الحلقة غير موجودة أو تم حذفها أثناء التنظيف.")
        return
    title, ep = res[0]
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (str(v_id),), fetch=False)
    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 القناة الإحتياطية", url=BACKUP_CHANNEL_LINK)]])
    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)

@api.get("/api/episodes")
def get_episodes_for_web():
    rows = db_query("SELECT v_id, title, ep_num FROM videos WHERE status='posted' ORDER BY v_id DESC LIMIT 30")
    data = [{"id": base64.b64encode(str(r[0]).encode()).decode(), "title": str(r[1]), "episode": r[2]} for r in rows]
    return JSONResponse(content=data, media_type="application/json; charset=utf-8")

# ===== [4] الأوامر والنشر =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        param = message.command[1]
        try:
            v_id = base64.b64decode(param).decode()
        except:
            v_id = param
        await show_episode(client, message, v_id)
    else:
        await message.reply_text("👋 أهلاً بك يا محمد. البوت والموقع يعملان الآن بأسماء نظيفة.")

@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
        await message.reply_text(f"✅ تم استلام الفيديو `{message.id}`")
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            raw_caption = message.caption if message.caption else "عنوان غير معروف"
            clean_title = raw_caption.split('\n')[0].strip() 
            db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (clean_title, message.photo.file_id, res[0][0]), fetch=False)
            await message.reply_text(f"🖼️ تم حفظ العنوان: {clean_title}")
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]; ep_num = int(message.text)
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
            me = await client.get_me()
            encoded_id = base64.b64encode(str(v_id).encode()).decode()
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ شاهد الآن", url=f"https://t.me/{me.username}?start={encoded_id}")]])
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep_num}]</b>", reply_markup=markup)

def run_api():
    uvicorn.run(api, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    init_database()
    clean_old_data() # تنظيف وتصحيح الأسماء عند التشغيل
    threading.Thread(target=run_api, daemon=True).start()
    app.run()
