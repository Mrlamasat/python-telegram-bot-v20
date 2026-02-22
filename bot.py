import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters

# ==============================
# 🔐 قراءة البيانات من المتغيرات
# ==============================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
DATABASE_URL = os.getenv("DATABASE_URL")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")

app = Client(
    "main_bot",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    sleep_threshold=60
)

# ==============================
# 📦 قاعدة البيانات
# ==============================
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
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
        print("DB Error:", e)
        return None
    finally:
        if conn:
            conn.close()

# ==============================
# 🔒 تشفير العنوان
# ==============================
def encrypt_text(text):
    if not text:
        return ""
    return "•".join(list(text))

# ==============================
# 🎬 عند رفع فيديو
# ==============================
@app.on_message(filters.chat(CHANNEL_USERNAME) & filters.video)
async def handle_new_video(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"video_{v_id}")

    db_query(
        """
        INSERT INTO episodes (v_id, title)
        VALUES (%s, %s)
        ON CONFLICT (v_id)
        DO UPDATE SET title=EXCLUDED.title
        """,
        (v_id, safe_title),
        commit=True
    )

    print(f"✅ تم حفظ الفيديو {v_id}")

# ==============================
# 🔄 عند تعديل الوصف
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

    print(f"🔄 تم تحديث الفيديو {v_id}")

# ==============================
# 🔎 البحث الخاص
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
            except:
                pass

print("🚀 البوت يعمل الآن على السيرفر...")
app.run()
