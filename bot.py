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

# ===== [3] عرض الحلقة (مباشرة من البيانات التي رفعها Termux) =====
async def show_episode(client, message, v_id):
    # جلب بيانات الحلقة التي حقنها Termux في القاعدة
    res = db_query("SELECT title FROM videos WHERE v_id = %s", (str(v_id),))
    
    title = res[0][0] if res else "حلقة مستعادة"
    
    try:
        caption = f"<b>📺 {title}</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 القناة الإحتياطية", url=BACKUP_CHANNEL_LINK)]])
        # إرسال الفيديو باستخدام رقم الـ ID الذي وفره Termux
        await client.copy_message(message.chat.id, SOURCE_CHANNEL_ID, int(v_id), caption=caption, reply_markup=markup)
    except Exception as e:
        logging.error(f"Send Error: {e}")
        await message.reply_text("❌ عذراً، تعذر جلب الفيديو. تأكد أن البوت لا يزال مشرفاً في القناة.")

# ===== [4] الأوامر والـ API =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        param = message.command[1]
        try: v_id = base64.b64decode(param).decode()
        except: v_id = param
        await show_episode(client, message, v_id)
    else:
        await message.reply_text("👋 البوت يعمل بنجاح! جميع الحلقات الـ 791 جاهزة للعرض.")

@api.get("/api/episodes")
def get_episodes_for_web():
    # جلب الحلقات التي تم حقنها بواسطة Termux
    rows = db_query("SELECT v_id, title FROM videos WHERE status='posted' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 100")
    data = [{"id": base64.b64encode(str(r[0]).encode()).decode(), "title": str(r[1])} for r in rows]
    return JSONResponse(content=data)

def run_api():
    uvicorn.run(api, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    threading.Thread(target=run_api, daemon=True).start()
    app.run()
