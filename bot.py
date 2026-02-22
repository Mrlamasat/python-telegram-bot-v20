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
ADMIN_CHANNEL_USERNAME = "Ramadan4kTV"  # أو id القناة -100xxx
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# ==============================
# 2. إعداد العميل
# ==============================
SESSION_STRING = os.environ.get("USER_SESSION")  # ضع هنا الـ session string
if not SESSION_STRING:
    raise ValueError("❌ USER_SESSION فارغ!")

app = Client(
    "my_session",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    workers=20,
    in_memory=True
)

# ==============================
# 3. دوال مساعدة
# ==============================
def hide_text(text):
    if not text: return "‌"
    return "‌".join(list(text))

def center_style(text):
    spacer = "ㅤ" * 5
    return f"{spacer}{text}{spacer}"

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
# 4. أمر استيراد الحلقات القديمة
# ==============================
@app.on_message(filters.command("import_old") & filters.private)
async def import_old(client, message):
    status = await message.reply_text("🔄 جاري الاتصال بالقناة وبدء السحب...")
    count = 0
    try:
        target_chat = await client.get_chat(ADMIN_CHANNEL_USERNAME)
        async for msg in client.get_chat_history(target_chat.id):
            if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                continue

            caption = (msg.caption or "").strip()
            if not caption: continue

            clean_title = caption.split('\n')[0].replace('🎬', '').strip()
            nums = re.findall(r'\d+', caption)
            ep_num = int(nums[0]) if nums else 1
            quality = "1080p" if "1080" in caption else "720p"

            # إضافة/تحديث المسلسل
            existing_series = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
            if existing_series:
                series_id = existing_series['id']
            else:
                db_query("INSERT INTO series (title) VALUES (%s)", (clean_title,), commit=True)
                res = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                series_id = res['id'] if res else None

            # إدخال الحلقة
            if series_id:
                db_query("""
                    INSERT INTO episodes (v_id, series_id, title, ep_num, duration, quality)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num
                """, (str(msg.id), series_id, clean_title, ep_num, "0:00", quality), commit=True)
                count += 1
                if count % 10 == 0:
                    await status.edit_text(f"🔄 جاري العمل.. تم سحب {count} حلقة حتى الآن.")

        await status.edit_text(f"✅ تم بنجاح! سحب {count} حلقة وربطها بالمسلسلات.")
    except Exception as e:
        await status.edit_text(f"❌ حدث خطأ أثناء السحب: {e}")

# ==============================
# 5. تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت بدأ العمل الآن...")
    app.run()
