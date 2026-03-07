import os
import psycopg2
import logging
import base64
import threading
import re
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

# ===== [3] وظيفة فك التشفير الذكية =====
def smart_decode(param):
    # محاولة فك التشفير العادي
    try:
        # إضافة الحشوة المفقودة (Padding) إذا لزم الأمر
        missing_padding = len(param) % 4
        if missing_padding:
            param += '=' * (4 - missing_padding)
        decoded = base64.b64decode(param).decode('utf-8', errors='ignore')
        # استخراج الأرقام فقط من النتيجة
        numbers = re.findall(r'\d+', decoded)
        return numbers[0] if numbers else None
    except:
        # إذا فشل التشفير، نحاول استخراج الأرقام مباشرة من النص (للحالات التي لا تشفر)
        numbers = re.findall(r'\d+', param)
        return numbers[0] if numbers else None

# ===== [4] إرسال الحلقة =====
async def send_video_safe(client, chat_id, raw_param):
    v_id = smart_decode(raw_param)
    
    if not v_id:
        logging.error(f"Could not extract ID from: {raw_param}")
        return False

    try:
        video_message_id = int(v_id)
        res = db_query("SELECT title FROM videos WHERE v_id = %s", (str(video_message_id),))
        title = res[0][0] if res else "حلقة مستعادة"
        
        caption = f"<b>📺 {title}</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 القناة الإحتياطية", url=BACKUP_CHANNEL_LINK)]])
        
        await client.copy_message(chat_id, SOURCE_CHANNEL_ID, video_message_id, caption=caption, reply_markup=markup)
        return True
    except Exception as e:
        logging.error(f"Send Error for ID {v_id}: {e}")
        return False

# ===== [5] الأوامر =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        param = message.command[1]
        success = await send_video_safe(client, message.chat.id, param)
        if not success:
            await message.reply_text("⚠️ الرابط قديم جداً أو غير صالح. جرب فتح الحلقة من الموقع مباشرة.")
    else:
        await message.reply_text("👋 البوت جاهز. الروابط القديمة تم تحديث نظام معالجتها الآن.")

@app.on_message(filters.forwarded & filters.private)
async def handle_activation(client, message):
    if message.forward_from_chat and message.forward_from_chat.id == SOURCE_CHANNEL_ID:
        await message.reply_text("✅ تم تنشيط الاتصال بالقناة بنجاح!")

# API للموقع
@api.get("/api/episodes")
def get_episodes_for_web():
    rows = db_query("SELECT v_id, title FROM videos WHERE status='posted' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 150")
    data = []
    for r in rows:
        # تشفير نظيف بدون رموز غريبة للموقع الجديد
        clean_id = base64.b64encode(str(r[0]).encode()).decode().replace('=', '')
        data.append({"id": clean_id, "title": str(r[1])})
    return JSONResponse(content=data)

def run_api():
    uvicorn.run(api, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    threading.Thread(target=run_api, daemon=True).start()
    app.run()
