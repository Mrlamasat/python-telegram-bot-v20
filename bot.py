import asyncio
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters

# ==============================
# 🔐 إعدادات (ضع بياناتك هنا)
# ==============================

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "ضع_توكن_البوت_هنا"

DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
CHANNEL_USERNAME = "@Ramadan4kTV"

# ==============================
# 🚀 تشغيل البوت
# ==============================

app = Client(
    "railway_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==============================
# 📦 دالة قاعدة البيانات
# ==============================

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            sslmode="require"
        )
        cur = conn.cursor()
        cur.execute(query, params)

        if fetchone:
            result = cur.fetchone()
        elif fetchall:
            result = cur.fetchall()
        else:
            result = None

        if commit:
            conn.commit()

        cur.close()
        return result

    except Exception as e:
        print("DB ERROR:", e)
        return None

    finally:
        if conn:
            conn.close()

# ==============================
# 🔒 تشفير الاسم
# ==============================

def encrypt_text(text):
    return "•".join(list(text))

# ==============================
# 🎬 عند نشر فيديو جديد
# ==============================

@app.on_message(filters.chat(CHANNEL_USERNAME) & filters.video)
async def handle_new_video(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"video_{v_id}")

    db_query(
        "INSERT INTO episodes (v_id, title) VALUES (%s, %s) "
        "ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title",
        (v_id, safe_title),
        commit=True
    )

    print("✅ تم حفظ فيديو جديد:", v_id)

# ==============================
# 🔄 عند تعديل وصف الفيديو
# ==============================

@app.on_edited_message(filters.chat(CHANNEL_USERNAME) & filters.video)
async def handle_edit(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"video_{v_id}")

    db_query(
        "UPDATE episodes SET title=%s WHERE v_id=%s",
        (safe_title, v_id),
        commit=True
    )

    print("🔄 تم تحديث عنوان الفيديو:", v_id)

# ==============================
# 🔍 البحث في الخاص
# ==============================

@app.on_message(filters.private & filters.text & ~filters.me & ~filters.outgoing)
async def search_bot(client, message):
    txt = message.text.strip()
    if len(txt) < 2:
        return

    search_query = f"%{encrypt_text(txt)}%"

    results = db_query(
        "SELECT v_id FROM episodes WHERE title ILIKE %s LIMIT 5",
        (search_query,),
        fetchall=True
    )

    if results:
        for res in results:
            try:
                await app.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=CHANNEL_USERNAME,
                    message_id=int(res["v_id"])
                )
                await asyncio.sleep(1)
            except Exception as e:
                print("Copy error:", e)

# ==============================
# ▶️ تشغيل
# ==============================

if __name__ == "__main__":
    print("🚀 البوت يعمل الآن على Railway بنجاح...")
    app.run()
