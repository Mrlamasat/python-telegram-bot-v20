import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters

# ==============================
# 🔐 إعدادات البوت من البيئة
# ==============================
SESSION_STRING = os.getenv("SESSION_STRING")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_CHANNEL = int(os.getenv("ADMIN_CHANNEL", "-1003547072209"))
PUBLIC_CHANNELS = os.getenv("PUBLIC_CHANNELS", "@MoAlmohsen,@RamadanSeries26").split(",")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

app = Client(
    "user_bot",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    sleep_threshold=60
)

# ==============================
# 🔒 دالات مساعدة
# ==============================
def encrypt_text(text):
    return "•".join(list(text)) if text else ""

def db_query(query, params=(), fetchone=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchone() if fetchone else None
        if commit: conn.commit()
        cur.close()
        return res
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# ==============================
# 1️⃣ سحب الفيديوهات الجديدة تلقائيًا
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
    # النشر التلقائي في القنوات العامة
    for ch in PUBLIC_CHANNELS:
        try:
            await client.copy_message(chat_id=ch, from_chat_id=ADMIN_CHANNEL, message_id=int(v_id))
            await asyncio.sleep(1)
        except Exception as e:
            print(f"❌ خطأ أثناء النشر للقناة {ch}: {e}")
    print(f"📥 تم سحب ونشر الحلقة الجديدة: {v_id}")

# ==============================
# 2️⃣ تحديث الفيديوهات المعدلة
# ==============================
@app.on_edited_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def handle_edit(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    db_query("UPDATE episodes SET title=%s WHERE v_id=%s", (safe_title, v_id), commit=True)
    print(f"🔐 تم تحديث اسم الحلقة: {v_id}")

# ==============================
# 3️⃣ نظام البحث الصامت
# ==============================
@app.on_message(filters.private & filters.text & ~filters.me & ~filters.outgoing)
async def search_bot(client, message):
    txt = message.text.strip()
    if len(txt) < 2:
        return
    
    search_query = f"%{encrypt_text(txt)}%"
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT v_id FROM episodes WHERE title ILIKE %s LIMIT 5", (search_query,))
        results = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ خطأ أثناء البحث: {e}")
        return

    if results:
        for res in results:
            try:
                await app.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=ADMIN_CHANNEL,
                    message_id=int(res['v_id'])
                )
                await asyncio.sleep(1)
            except Exception as e:
                print(f"❌ خطأ أثناء إرسال النتائج للمستخدم: {e}")

# ==============================
# ▶️ تشغيل البوت مع طباعة الأخطاء
# ==============================
if __name__ == "__main__":
    try:
        print("🚀 البوت يعمل الآن على الاستضافة...")
        app.run()
    except Exception as e:
        print("❌ حدث خطأ أثناء تشغيل البوت:", e)
