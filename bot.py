import logging
import psycopg2
import asyncio
import os
import re
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==============================
# 1. الإعدادات
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
ADMIN_CHANNEL = "Ramadan4kTV"  # استخدم اسم القناة بدل ID
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# ==============================
# 2. إعداد العميل
# ==============================
SESSION_STRING = os.environ.get("USER_SESSION")
if not SESSION_STRING:
    raise ValueError("❌ USER_SESSION فارغ! ضعها في Variable Variables")

app = Client(
    name="my_session",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    workers=20,
    in_memory=True
)

# ==============================
# 3. دالات مساعدة
# ==============================
def hide_text(text):
    return "‌".join(list(text)) if text else "‌"

def center_style(text):
    return f"{'ㅤ'*5}{text}{'ㅤ'*5}"

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
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
# 4. استيراد الفيديوهات القديمة
# ==============================
@app.on_message(filters.command("import_updated") & filters.private)
async def import_updated_series(client, message):
    status = await message.reply_text("🔄 جاري سحب الفيديوهات القديمة...")
    count = 0
    try:
        chat = await client.get_chat(ADMIN_CHANNEL)
        async for msg in client.get_chat_history(chat.id):
            if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                continue

            caption = (msg.caption or "").strip()
            title = caption.split('\n')[0].replace('🎬', '').strip() if caption else f"مسلسل-{msg.id}"
            ep_num = int(re.findall(r'\d+', caption)[0]) if re.findall(r'\d+', caption) else 1
            quality = "1080p" if "1080" in caption else "720p"

            series = db_query("SELECT id FROM series WHERE title=%s", (title,), fetchone=True)
            if not series:
                db_query("INSERT INTO series (title) VALUES (%s)", (title,), commit=True)
                series = db_query("SELECT id FROM series WHERE title=%s", (title,), fetchone=True)
            if series:
                db_query(
                    "INSERT INTO episodes (v_id, series_id, title, ep_num, duration, quality) VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num",
                    (str(msg.id), series['id'], title, ep_num, "0:00", quality),
                    commit=True
                )
                count += 1
                if count % 10 == 0:
                    await status.edit_text(f"🔄 جاري العمل.. تم سحب {count} حلقة")

        await status.edit_text(f"✅ تم سحب {count} حلقة وربطها بالمسلسلات.")
    except Exception as e:
        await status.edit_text(f"❌ حدث خطأ أثناء السحب: {e}")

# ==============================
# 5. رفع فيديو جديد (كما كان سابقاً)
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query(
        "INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s,%s,%s,'awaiting_poster') "
        "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
        (message.chat.id, v_id, f"{duration//60}:{duration%60:02d}"), commit=True
    )
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن")

# ==============================
# 6. باقي وظائف البوت كما هي
# ==============================
# (بوسترات، اختيار الجودة، نشر في القنوات، نظام /start للعضو ...)
# يمكنك نسخ باقي الكود كما هو لديك حالياً

# ==============================
# 7. تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت بدأ العمل الآن...")
    app.run()
