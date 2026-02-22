import logging
import psycopg2
import asyncio
import re
from psycopg2.extras import RealDictCursor
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 1. الإعدادات
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
SESSION_STRING = "BAIcPawAqsz8F_p2JJmXjf2wJeeg2frJbPyA1FfK3gb4urW94P9VCR5N5apDGsEmeJxtehLGkZs7of6guY6fUqlhG3AnvjVKlxCAHA_xja75TxKgIRqUi-GcjFb_JSguFGioFPTIeX5donwup7_TXxfxCqNURpL_4EPenFnqc6EEbOhRa5Wz7rqE7kv-0KznphGohGYovuftOxoZhUAv0ASyD_pYjcyFBn6798_tmUa-LZyluuxY_msjiigO35H0V8gukbedFVezTLBsuoY6iK61mwXHFeFEkczFfOlEXNp-_ZmU4uBSuFqRdaZOLaRAeaXKoX2eWruWCmCY9bq-VErWbe6GTQAAAAHMKGDXAA"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
ADMIN_CHANNEL = -1001555555555  # ضع رقم القناة هنا
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# ==============================
# 2. إعداد العميل
# ==============================
app = Client(
    name="my_bot_session",
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
    return "‌".join(list(text)) if text else "‌"

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
# 4. سحب الفيديوهات القديمة تلقائياً
# ==============================
async def import_old_videos():
    print("🔄 بدء سحب الفيديوهات القديمة...")
    count = 0
    try:
        chat = await app.get_chat(ADMIN_CHANNEL)
        async for msg in app.get_chat_history(chat.id):
            # تجاهل الرسائل الغير فيديو
            if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                continue

            caption = (msg.caption or "").strip()
            clean_title = caption.split("\n")[0] if caption else "مسلسل بدون اسم"
            nums = re.findall(r'\d+', caption)
            ep_num = int(nums[0]) if nums else 1
            quality = "1080p" if "1080" in caption else ("720p" if "720" in caption else "1080p")

            # إضافة أو تحديث المسلسل
            existing_series = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
            if existing_series:
                series_id = existing_series['id']
            else:
                db_query("INSERT INTO series (title) VALUES (%s)", (clean_title,), commit=True)
                series_id = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)['id']

            # إدخال الحلقة
            db_query("""
                INSERT INTO episodes (v_id, series_id, title, ep_num, duration, quality)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (v_id) DO UPDATE SET ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality
            """, (str(msg.id), series_id, clean_title, ep_num, "0:00", quality), commit=True)
            count += 1
            if count % 10 == 0:
                print(f"🔄 تم سحب {count} حلقة حتى الآن...")

        print(f"✅ تم الانتهاء! تم سحب {count} حلقة وربطها بالمسلسلات.")
    except Exception as e:
        print(f"❌ حدث خطأ أثناء السحب: {e}")

# ==============================
# 5. تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت بدأ العمل الآن...")
    with app:
        asyncio.get_event_loop().run_until_complete(import_old_videos())
