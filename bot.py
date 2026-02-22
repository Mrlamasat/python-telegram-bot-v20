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
BOT_SESSION = "BAIcPawAqsz8F_p2JJmXjf2wJeeg2frJbPyA1FfK3gb4urW94P9VCR5N5apDGsEmeJxtehLGkZs7of6guY6fUqlhG3AnvjVKlxCAHA_xja75TxKgIRqUi-GcjFb_JSguFGioFPTIeX5donwup7_TXxfxCqNURpL_4EPenFnqc6EEbOhRa5Wz7rqE7kv-0KznphGohGYovuftOxoZhUAv0ASyD_pYjcyFBn6798_tmUa-LZyluuxY_msjiigO35H0V8gukbedFVezTLBsuoY6iK61mwXHFeFEkczFfOlEXNp-_ZmU4uBSuFqRdaZOLaRAeaXKoX2eWruWCmCY9bq-VErWbe6GTQAAAAHMKGDXAA"

API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
ADMIN_CHANNEL = -1003547072209
PUBLIC_CHANNELS = ["@Ramadan4kTV", "@MoAlmohsen"]
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# ==============================
# 2. إعداد العميل
# ==============================
app = Client(
    session_string=BOT_SESSION,
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
# 4. أمر سحب الفيديوهات القديمة
# ==============================
@app.on_message(filters.command("import_updated") & filters.private)
async def import_updated(client, message):
    await message.reply_text("🔄 بدء سحب الفيديوهات القديمة...")
    count = 0
    try:
        target_chat = await client.get_chat(PUBLIC_CHANNELS[0])
        async for msg in client.get_chat_history(target_chat.id):
            if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                continue
            caption = (msg.caption or "").strip()
            clean_title = caption.split("\n")[0].replace('🎬','').strip()
            nums = re.findall(r'\d+', caption)
            ep_num = int(nums[0]) if nums else 1
            quality = "1080p"
            if "720" in caption: quality = "720p"

            existing_series = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
            if existing_series:
                series_id = existing_series['id']
            else:
                db_query("INSERT INTO series (title) VALUES (%s)", (clean_title,), commit=True)
                res = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                series_id = res['id'] if res else None

            if series_id:
                db_query(
                    """
                    INSERT INTO episodes (v_id, series_id, title, ep_num, duration, quality)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num
                    """,
                    (str(msg.id), series_id, clean_title, ep_num, "0:00", quality), commit=True
                )
                count += 1
                if count % 10 == 0:
                    await message.reply_text(f"🔄 تم سحب {count} حلقة حتى الآن.")

        await message.reply_text(f"✅ تم الانتهاء! تم سحب {count} حلقة وربطها بالمسلسلات.")
    except Exception as e:
        await message.reply_text(f"❌ حدث خطأ أثناء السحب: {e}")

# ==============================
# 5. تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت بدأ العمل الآن...")
    app.run()
