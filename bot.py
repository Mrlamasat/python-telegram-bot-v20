from pyrogram import Client, filters
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import asyncio

# ==============================
# 🔐 المتغيرات من البيئة
# ==============================
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_CHANNEL = int(os.environ.get("ADMIN_CHANNEL", "-1000000000000"))
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")  # @MoAlmohsen,@RamadanSeries26
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH")

# ==============================
# 🛠 التأكد من وجود المتغيرات
# ==============================
if not all([SESSION_STRING, DATABASE_URL, ADMIN_CHANNEL, API_ID, API_HASH]):
    raise ValueError("❌ أحد متغيرات البيئة مفقود. تحقق من SESSION_STRING, DATABASE_URL, ADMIN_CHANNEL, API_ID, API_HASH.")

# ==============================
# 🔹 البوت
# ==============================
app = Client(
    "mo_user_bot",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    sleep_threshold=60
)

def encrypt_text(text):
    return "•".join(list(text)) if text else ""

def db_query(query, params=(), commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(query, params)
        if commit: conn.commit()
        cur.close()
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        if conn: conn.close()

# ==============================
# 📥 مراقبة القناة وسحب الحلقات
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def handle_new_video(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    db_query(
        "INSERT INTO episodes (v_id, title) VALUES (%s, %s) "
        "ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title",
        (v_id, safe_title),
        commit=True
    )
    # نشر تلقائي في القنوات العامة
    for ch in PUBLIC_CHANNELS:
        try:
            await client.copy_message(ch, ADMIN_CHANNEL, message.id)
        except: pass
    print(f"📥 تم سحب ونشر حلقة جديدة: {v_id}")

@app.on_edited_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def handle_edit(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    db_query("UPDATE episodes SET title=%s WHERE v_id=%s", (safe_title, v_id), commit=True)
    print(f"🔐 تم تحديث اسم الحلقة: {v_id}")

# ==============================
# 🔍 البحث الصامت
# ==============================
@app.on_message(filters.private & filters.text & ~filters.me & ~filters.outgoing)
async def search_bot(client, message):
    txt = message.text.strip()
    if len(txt) < 2: return
    search_query = f"%{encrypt_text(txt)}%"
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT v_id FROM episodes WHERE title ILIKE %s LIMIT 5", (search_query,))
    results = cur.fetchall()
    cur.close()
    conn.close()
    if results:
        for res in results:
            try:
                await app.copy_message(chat_id=message.chat.id, from_chat_id=ADMIN_CHANNEL, message_id=int(res['v_id']))
                await asyncio.sleep(1)
            except: pass

# ==============================
# ▶️ تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت يعمل الآن على الاستضافة...")
    app.run()
