import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters

# ==============================
# 🔐 جلب المتغيرات من البيئة
# ==============================
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL = os.environ.get("DATABASE_URL")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
ADMIN_CHANNEL = int(os.environ.get("ADMIN_CHANNEL", "0"))
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")  # قنوات للنشر التلقائي

# التحقق من وجود كل المتغيرات
if not all([SESSION_STRING, DATABASE_URL, BOT_TOKEN, API_ID, API_HASH, ADMIN_CHANNEL]):
    raise ValueError("❌ أحد متغيرات البيئة مفقود. تحقق من SESSION_STRING, DATABASE_URL, ADMIN_CHANNEL, API_ID, API_HASH.")

# ==============================
# 📦 إنشاء البوت
# ==============================
app = Client(
    "mo_user_bot",
    session_string=SESSION_STRING,
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=60
)

# ==============================
# 🔒 دوال مساعدة
# ==============================
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
# 📥 سحب حلقات جديدة من القناة
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def handle_new_video(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    db_query(
        "INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title",
        (v_id, safe_title),
        commit=True
    )
    print(f"📥 تم سحب حلقة جديدة تلقائياً: {v_id}")

    # نشر الحلقة تلقائيًا في القنوات العامة
    for channel in PUBLIC_CHANNELS:
        try:
            await app.copy_message(chat_id=channel.strip(), from_chat_id=ADMIN_CHANNEL, message_id=int(v_id))
            await asyncio.sleep(1)
        except Exception as e:
            print(f"❌ خطأ في النشر للقناة {channel}: {e}")

# ==============================
# 🔄 تحديث الحلقات عند تعديلها
# ==============================
@app.on_edited_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def handle_edit(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    db_query("UPDATE episodes SET title=%s WHERE v_id=%s", (safe_title, v_id), commit=True)
    print(f"🔄 تم تحديث اسم الحلقة: {v_id}")

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
                await app.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=ADMIN_CHANNEL,
                    message_id=int(res['v_id'])
                )
                await asyncio.sleep(1)
            except: pass

# ==============================
# ▶ تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت يعمل الآن على الاستضافة...")
    app.run()
