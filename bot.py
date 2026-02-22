# bot.py
import asyncio
from pyrogram import Client, idle
import os
import psycopg2

# -----------------------------
# إعداد متغيرات البيئة
# -----------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
SOURCE_CHANNEL = os.environ.get("SOURCE_CHANNEL")
DATABASE_URL = os.environ.get("DATABASE_URL")

# -----------------------------
# إعداد قاعدة البيانات
# -----------------------------
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

def db_query(query, params=None, commit=False):
    cursor.execute(query, params or ())
    if commit:
        conn.commit()
    return cursor.fetchall() if cursor.description else None

# -----------------------------
# إعداد البوت
# -----------------------------
app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    session_string=SESSION_STRING,
)

# -----------------------------
# دالة جلب الحلقات القديمة
# -----------------------------
async def fetch_old_videos(client):
    print("⏳ جاري جلب الحلقات القديمة...")
    try:
        async for message in client.get_chat_history(SOURCE_CHANNEL, limit=200):
            if not message.video:
                continue
            v_id = str(message.id)
            title = message.caption or f"فيديو {v_id}"
            poster_id = message.photo.file_id if message.photo else None
            db_query(
                """
                INSERT INTO episodes (v_id, title, poster_id) 
                VALUES (%s, %s, %s)
                ON CONFLICT (v_id) DO UPDATE 
                SET title=EXCLUDED.title, poster_id=EXCLUDED.poster_id
                """,
                (v_id, title, poster_id),
                commit=True
            )
            print(f"📥 تم جلب حلقة قديمة: {v_id}")
        print("✅ تم الانتهاء من جلب الحلقات القديمة.")
    except Exception as e:
        print(f"⚠️ حدث خطأ أثناء جلب الحلقات القديمة: {e}")

# -----------------------------
# الدالة الرئيسية لتشغيل البوت
# -----------------------------
def run_bot():
    while True:
        try:
            print("🚀 تشغيل البوت...")
            app.start()
            # جلب الحلقات القديمة
            app.loop.run_until_complete(fetch_old_videos(app))
            # البوت يظل يعمل
            idle()
        except Exception as e:
            print(f"⚠️ البوت توقف بسبب خطأ: {e}")
            print("⏳ سيتم إعادة التشغيل خلال 5 ثوانٍ...")
            asyncio.sleep(5)
        finally:
            app.stop()

# -----------------------------
# بدء التشغيل
# -----------------------------
if __name__ == "__main__":
    run_bot()
