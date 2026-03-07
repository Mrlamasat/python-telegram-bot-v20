import os
import psycopg2
import logging
import base64
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

SOURCE_CHANNEL_ID = -1003547072209 
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
api = FastAPI()

api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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

# ===== [3] وظيفة إرسال الحلقة =====
async def send_video_safe(client, chat_id, v_id_str):
    try:
        # التأكد من أن الـ ID هو رقم صحيح
        video_message_id = int(v_id_str)
        
        res = db_query("SELECT title FROM videos WHERE v_id = %s", (str(video_message_id),))
        title = res[0][0] if res else "حلقة مستعادة"
        
        caption = f"<b>📺 {title}</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 القناة الإحتياطية", url=BACKUP_CHANNEL_LINK)]])
        
        await client.copy_message(chat_id, SOURCE_CHANNEL_ID, video_message_id, caption=caption, reply_markup=markup)
    except Exception as e:
        logging.error(f"Send Error: {e}")
        return False
    return True

# ===== [4] الأوامر ومعالجة الروابط =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        param = message.command[1]
        try:
            # محاولة فك التشفير بأمان
            v_id = base64.b64decode(param).decode()
        except:
            v_id = param
            
        success = await send_video_safe(client, message.chat.id, v_id)
        if not success:
            await message.reply_text("⚠️ لم يتمكن البوت من الوصول للحلقة. يرجى تحويل أي رسالة من القناة المصدر للبوت لتنشيطه.")
    else:
        await message.reply_text("👋 البوت جاهز لعرض الحلقات المستعادة من Termux.")

# معالجة التحويل (تنشيط القناة)
@app.on_message(filters.forwarded & filters.private)
async def handle_activation(client, message):
    if message.forward_from_chat and message.forward_from_chat.id == SOURCE_CHANNEL_ID:
        await message.reply_text("✅ ممتاز! تم تنشيط الاتصال بالقناة بنجاح. الآن جميع الروابط ستعمل.")
    else:
        await message.reply_text(f"معرف القناة المحولة: {message.forward_from_chat.id if message.forward_from_chat else 'غير معروف'}")

@api.get("/api/episodes")
def get_episodes_for_web():
    rows = db_query("SELECT v_id, title FROM videos WHERE status='posted' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 100")
    data = []
    for r in rows:
        encoded_id = base64.b64encode(str(r[0]).encode()).decode().replace('=', '')
        data.append({"id": encoded_id, "title": str(r[1])})
    return JSONResponse(content=data)

def run_api():
    uvicorn.run(api, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    threading.Thread(target=run_api, daemon=True).start()
    app.run()
