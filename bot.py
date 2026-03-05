import os
import psycopg2
import psycopg2.pool
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# الإعدادات
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# أهم خطوة: استبدال postgresql بـ postgres تلقائياً
DATABASE_URL = os.environ.get("DATABASE_URL").replace("postgresql://", "postgres://")

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# دالة بسيطة جداً للاتصال بقاعدة البيانات
def get_video_data(v_id):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT title, ep_num, quality, duration, file_id FROM videos WHERE v_id=%s", (v_id,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return None

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    try:
        if len(message.command) < 2:
            return await message.reply_text("أهلاً بك في بوت المسلسلات! 👋")

        v_id = message.command[1]
        data = get_video_data(v_id)
        
        if data:
            title, ep, q, dur, f_id = data
            cap = f"<b>📺 {title}</b>\n<b>🎞️ حلقة: {ep}</b>\n<b>💿 جودة: {q}</b>"
            
            if f_id:
                await client.send_video(message.chat.id, video=f_id, caption=cap)
            else:
                await message.reply_text(f"🎬 {title} - حلقة {ep}\n(الملف موجود في المصدر، جاري التحديث)")
        else:
            await message.reply_text("❌ لم يتم العثور على بيانات هذا الفيديو.")
            
    except Exception as e:
        logging.error(f"Error in start: {e}")
        # نرسل أي رد لكي لا تظهر العلامة الحمراء
        await message.reply_text("⚠️ حدث خطأ تقني بسيط، يرجى المحاولة لاحقاً.")

# تشغيل البوت
if __name__ == "__main__":
    app.run()
