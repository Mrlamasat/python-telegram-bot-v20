# bot.py
import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters

# ==============================
# 🔐 الإعدادات من البيئة (GitHub Secrets)
# ==============================
SESSION_STRING = os.environ.get("SESSION_STRING")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH")
DATABASE_URL = os.environ.get("DATABASE_URL")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME")

# ==============================
# 🔗 إنشاء البوت
# ==============================
app = Client(
    "main_bot",
    session_string=SESSION_STRING,
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
    sleep_threshold=60
)

# ==============================
# 🔒 تشفير النصوص لتخزينها في DB
# ==============================
def encrypt_text(text):
    return "•".join(list(text))

# ==============================
# 📦 دالة قاعدة البيانات
# ==============================
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None)
        if commit: conn.commit()
        cur.close()
        return result
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# ==============================
# 🔄 تحديث الفيديوهات القديمة والجديدة
# ==============================
async def update_videos():
    print("🔄 فحص القناة وتحديث الفيديوهات...")
    count = 0
    async for message in app.get_chat_history(CHANNEL_USERNAME, limit=5000):
        if not message.video:
            continue

        v_id = str(message.id)
        duration = getattr(message.video, "duration", 0)
        poster_id = message.photo.file_id if message.photo else None
        title = message.caption if message.caption else f"فيديو {v_id}"

        safe_title = encrypt_text(title)

        db_query(
            """INSERT INTO episodes (v_id, poster_id, title, duration) 
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (v_id) DO UPDATE 
               SET poster_id=EXCLUDED.poster_id, title=EXCLUDED.title, duration=EXCLUDED.duration""",
            (v_id, poster_id, safe_title, duration),
            commit=True
        )
        count += 1

    print(f"✅ انتهى التحديث. تم تحديث/إضافة {count} حلقة.")

# ==============================
# 📝 تحديث العنوان عند تعديل الفيديو
# ==============================
@app.on_edited_message(filters.chat(CHANNEL_USERNAME) & filters.video)
async def handle_edit(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    db_query(
        "UPDATE episodes SET title=%s WHERE v_id=%s",
        (safe_title, v_id),
        commit=True
    )
    print(f"📝 تم تحديث العنوان للحلقة {v_id}")

# ==============================
# ➕ إضافة الفيديوهات الجديدة
# ==============================
@app.on_message(filters.chat(CHANNEL_USERNAME) & filters.video)
async def handle_new_video(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    poster_id = message.photo.file_id if message.photo else None
    duration = getattr(message.video, "duration", 0)

    db_query(
        """INSERT INTO episodes (v_id, poster_id, title, duration) 
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (v_id) DO UPDATE 
           SET poster_id=EXCLUDED.poster_id, title=EXCLUDED.title, duration=EXCLUDED.duration""",
        (v_id, poster_id, safe_title, duration),
        commit=True
    )
    print(f"➕ تم إضافة/تحديث الحلقة {v_id}")

# ==============================
# 🔍 البحث للمستخدمين
# ==============================
@app.on_message(filters.private & filters.text & ~filters.me & ~filters.outgoing)
async def search_bot(client, message):
    txt = message.text.strip()
    if len(txt) < 2:
        return

    search_query = f"%{encrypt_text(txt)}%"
    results = db_query(
        "SELECT v_id, title FROM episodes WHERE title ILIKE %s LIMIT 5",
        (search_query,),
        fetchall=True
    )

    if results:
        for res in results:
            try:
                await app.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=CHANNEL_USERNAME,
                    message_id=int(res['v_id'])
                )
                await asyncio.sleep(1)
            except Exception as e:
                print(f"❌ خطأ أثناء إرسال الحلقة {res['v_id']}: {e}")

# ==============================
# ▶️ تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت يعمل الآن على GitHub Actions...")
    app.start()
    asyncio.run(update_videos())
    app.idle()
