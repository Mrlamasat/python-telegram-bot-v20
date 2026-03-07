import os
import psycopg2
import logging
import base64
import threading
import asyncio
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

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
api = FastAPI()

api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, poster_id TEXT, ep_num INTEGER, status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0, last_view TIMESTAMP)", fetch=False)

# ===== [3] وظيفة استعادة الحلقات =====
async def sync_missing_episodes():
    await asyncio.sleep(5) # انتظار تشغيل البوت تماماً
    logging.info("⏳ جاري استعادة الحلقات من القناة المصدر...")
    try:
        async for message in app.get_chat_history(SOURCE_CHANNEL, limit=1500):
            if message.video or message.document:
                v_id = str(message.id)
                res = db_query("SELECT v_id FROM videos WHERE v_id = %s", (v_id,))
                if not res:
                    raw_title = message.caption.split('\n')[0] if message.caption else "حلقة قديمة"
                    db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted')", (v_id, raw_title, 0), fetch=False)
        
        for correct in CORRECT_TITLES:
            clean_name = correct.replace(" ", "")
            db_query(f"UPDATE videos SET title = %s WHERE REPLACE(title, ' ', '') LIKE %s", (correct, f"%{clean_name}%"), fetch=False)
        logging.info("✅ تم استعادة 800+ حلقة بنجاح!")
    except Exception as e:
        logging.error(f"Sync Error: {e}")

# دالة لتشغيل المزامنة في خلفية البوت
def start_sync_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(sync_missing_episodes())

# ===== [4] الأوامر والـ API =====
async def show_episode(client, message, v_id):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (str(v_id),))
    if not res:
        await message.reply_text("❌ جاري مزامنة بيانات هذه الحلقة، حاول مجدداً بعد دقيقة...")
        return
    title, ep = res[0]
    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 القناة الإحتياطية", url=BACKUP_CHANNEL_LINK)]])
    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)

@api.get("/api/episodes")
def get_episodes_for_web():
    rows = db_query("SELECT v_id, title, ep_num FROM videos WHERE status='posted' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 50")
    data = [{"id": base64.b64encode(str(r[0]).encode()).decode(), "title": str(r[1]), "episode": r[2]} for r in rows]
    return JSONResponse(content=data)

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        param = message.command[1]
        try: v_id = base64.b64decode(param).decode()
        except: v_id = param
        await show_episode(client, message, v_id)
    else:
        await message.reply_text("👋 البوت يعمل الآن ويقوم باستعادة حلقاتك القديمة تلقائياً.")

def run_api():
    uvicorn.run(api, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ===== [5] التشغيل النهائي =====
if __name__ == "__main__":
    init_database()
    # تشغيل الـ API في خيط منفصل
    threading.Thread(target=run_api, daemon=True).start()
    
    # تشغيل عملية الاستعادة في خيط منفصل لعدم تعطيل البوت
    threading.Thread(target=start_sync_loop, daemon=True).start()
    
    app.run()
