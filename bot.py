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

# تعديل المعرف هنا لحل مشكلة USERNAME_INVALID
ADMIN_CHANNEL = "@Ramadan4kTV" 
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# ==============================
# 2. إعداد العميل (الروبوت والحساب)
# ==============================
SESSION_STRING = os.environ.get("USER_SESSION")

# الحساب الشخصي (للسحب)
user_app = Client(
    name="user_session",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    in_memory=True
)

# البوت (للتفاعل مع الأعضاء)
bot_app = Client(
    name="bot_app",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
    in_memory=True
)

# --- دالة الاستعلام ---
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
# 3. أمر سحب الحلقات
# ==============================
@bot_app.on_message(filters.command("import_updated") & filters.private)
async def import_updated_series(client, message):
    status = await message.reply_text("🔄 جاري بدء السحب باستخدام الحساب الشخصي...")
    count = 0
    try:
        # تشغيل حساب المستخدم مؤقتاً للسحب
        if not user_app.is_connected:
            await user_app.start()

        target_chat = await user_app.get_chat(ADMIN_CHANNEL)

        async for msg in user_app.get_chat_history(target_chat.id):
            if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                continue

            caption = (msg.caption or "").strip()
            if not caption: continue

            clean_title = caption.split('\n')[0].replace('🎬', '').strip()
            nums = re.findall(r'\d+', caption)
            ep_num = int(nums[0]) if nums else 1

            # تحديث قاعدة البيانات
            db_query("INSERT INTO series (title) VALUES (%s) ON CONFLICT (title) DO NOTHING", (clean_title,), commit=True)
            s_res = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
            
            if s_res:
                db_query("""
                    INSERT INTO episodes (v_id, series_id, title, ep_num, quality)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num
                """, (str(msg.id), s_res['id'], clean_title, ep_num, "1080p"), commit=True)
                count += 1
                if count % 20 == 0:
                    await status.edit_text(f"🔄 جاري العمل.. تم سحب {count} حلقة.")

        await status.edit_text(f"✅ اكتمل السحب بنجاح! تم تحديث {count} حلقة.")
    except Exception as e:
        await status.edit_text(f"❌ حدث خطأ: {e}")

# ==============================
# 4. تشغيل الكل
# ==============================
async def main():
    await bot_app.start()
    print("🚀 البوت يعمل الآن...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
