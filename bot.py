# bot.py
import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters

# ==============================
# 🔐 الإعدادات من البيئة
# ==============================
SESSION_STRING = os.environ.get("SESSION_STRING")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME")

# ==============================
# 📦 تهيئة البوت
# ==============================
app = Client(
    "main_bot",
    session_string=SESSION_STRING,
    bot_token=BOT_TOKEN,
    api_id=int(os.environ.get("API_ID", 0)),      # ضع API_ID في Secrets
    api_hash=os.environ.get("API_HASH", ""),      # ضع API_HASH في Secrets
    sleep_threshold=60
)

# ==============================
# 🔒 تشفير النصوص (لإخفاء العنوان قليلاً)
# ==============================
def encrypt_text(text: str) -> str:
    return "•".join(list(text))

# ==============================
# 📦 دالة قاعدة البيانات
# ==============================
def db_query(query, params=(), fetchone=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchone() if fetchone else None
        if commit:
            conn.commit()
        cur.close()
        return res
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn:
            conn.close()

# ==============================
# ✏️ تحديث الفيديوهات المعدلة
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
    print(f"✏️ تم تحديث عنوان الحلقة {v_id}")

# ==============================
# ➕ إضافة الفيديوهات الجديدة
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
    print(f"➕ تم حفظ الحلقة الجديدة {v_id}")

# ==============================
# 🔎 البحث في البوت
# ==============================
@app.on_message(filters.private & filters.text & ~filters.me & ~filters.outgoing)
async def search_bot(client, message):
    txt = message.text.strip()
    if len(txt) < 2:
        return

    search_query = f"%{encrypt_text(txt)}%"
    results = db_query(
        "SELECT v_id, title FROM episodes WHERE title ILIKE %s LIMIT 5",
        (search_query,)
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
                print(f"⚠️ خطأ أثناء إرسال الحلقة {res['v_id']}: {e}")

# ==============================
# ▶️ تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت يعمل الآن باستخدام المتغيرات البيئية...")
    app.run()
