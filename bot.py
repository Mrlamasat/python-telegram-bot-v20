import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات لمراقبة المشاكل
logging.basicConfig(level=logging.INFO)

# ===== 1. الإعدادات (تأكد من وجودها في Railway Variables) =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# تصحيح الرابط برمجياً لضمان عدم التعليق
raw_db_url = os.environ.get("DATABASE_URL")
DATABASE_URL = raw_db_url.replace("postgresql://", "postgres://") if raw_db_url else None

ADMIN_ID = 7720165591
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003554018307
FORCE_SUB_LINK = "https://t.me/+PyUeOtPN1fs0NDA0"
PUBLIC_POST_CHANNEL = "@ramadan2206"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== 2. قاعدة البيانات (نسخة لا تسمح بالتعليق) =====
def db_query(query, params=(), fetch=True):
    conn = None
    try:
        # connect_timeout=3 تعني إذا لم يستجب السيرفر في 3 ثوانٍ اخرج فوراً (تمنع العلامة الحمراء)
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=3)
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ DB ERROR: {e}")
        return None
    finally:
        if conn: conn.close()

# ===== 3. معالج الـ START (معدل لكسر التعليق) =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    # الخطوة الأولى: رد سريع جداً لتأكيد الاستلام وإخفاء العلامة الحمراء
    try:
        if len(message.command) < 2:
            await message.reply_text(f"أهلاً {escape(message.from_user.first_name)}! ابحث عن الحلقات في القناة.")
            return

        v_id = message.command[1]
        
        # محاولة جلب البيانات من القاعدة
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        
        if res:
            title, ep, q, dur = res[0]
            # دالة الإرسال (تأكد أنها موجودة في كودك الكامل)
            await send_video_final(client, message.chat.id, message.from_user.id, v_id, title, ep, q, dur)
        else:
            await message.reply_text("⚠️ عذراً، لم نجد بيانات لهذه الحلقة. قد تكون قديمة جداً.")

    except Exception as e:
        logging.error(f"🔥 Start Crash: {e}")
        await message.reply_text("❌ حدث خطأ مؤقت، يرجى المحاولة مرة أخرى.")

# (أضف بقية الدوال: send_video_final, receive_video, إلخ هنا)

if __name__ == "__main__":
    app.run()
