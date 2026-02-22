import logging
import psycopg2
import asyncio
import os
import re
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 1. الإعدادات
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
ADMIN_CHANNEL = "https://t.me/Ramadan4kTV"  # تم تغيير ID إلى رابط القناة
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# ==============================
# 2. إعداد حساب شخصي (User Session) لتجاوز مشاكل الوصول للرسائل القديمة
# ==============================
SESSION_STRING = os.environ.get("USER_SESSION")
if not SESSION_STRING:
    raise ValueError("❌ USER_SESSION فارغ! تأكد من وضعه في Variable Variables")

user_client = Client(
    name="user_session",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    workers=20,
    in_memory=True
)

bot_app = Client(
    name="bot_app",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
    workers=20
)

# --- دالات المساعدة ---
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
# 3. سحب الحلقات القديمة
# ==============================
@bot_app.on_message(filters.command("import_updated") & filters.private)
async def import_updated_series(client, message):
    status = await message.reply_text("🔄 جاري الاتصال بالقناة وبدء السحب...")
    count = 0
    try:
        async with user_client:
            target_chat = await user_client.get_chat(ADMIN_CHANNEL)

            async for msg in user_client.get_chat_history(target_chat.id, limit=None):
                if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                    continue

                caption = (msg.caption or "").strip()
                if not caption:
                    continue

                clean_title = caption.split('\n')[0].replace('🎬', '').strip()
                nums = re.findall(r'\d+', caption)
                ep_num = int(nums[0]) if nums else 1
                quality = "1080p" if "1080" in caption else "720p" if "720" in caption else "غير محدد"

                # إنشاء/تحديث المسلسل
                existing_series = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                if existing_series:
                    series_id = existing_series['id']
                else:
                    db_query("INSERT INTO series (title) VALUES (%s)", (clean_title,), commit=True)
                    series_id = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)['id']

                # إضافة الحلقة
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
# 4. أوامر الإدارة والرفع اليدوي
# ==============================
@bot_app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query(
        "INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') "
        "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", 
        (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"), commit=True
    )
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن واكتب اسم المسلسل في الوصف.")

# ... (تكملة باقي كود البوت كما هو في النسخة السابقة)
# يمكنك إضافة بقية الوظائف: on_poster، on_num، publish، start إلخ بنفس الأسلوب السابق

if __name__ == "__main__":
    print("🚀 البوت بدأ العمل الآن...")
    bot_app.run()
