import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- الإعدادات (تأكد من وجودها في GitHub Secrets) ---
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")

SOURCE_CHANNEL  = "@Ramadan4kTV"  # القناة المصدرية
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

app = Client("my_bot", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)

# --- دالة قاعدة البيانات ---
def db_query(query, params=(), commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if commit: conn.commit()
        cur.close()
    except Exception as e:
        print(f"❌ خطأ في قاعدة البيانات: {e}")
    finally:
        if conn: conn.close()

# --- دالة المزامنة لجلب حلقات أمس (تم تصحيحها هنا) ---
async def fetch_old_videos():
    print("⏳ جاري فحص حلقات أمس من القناة المصدرية...")
    count = 0
    try:
        # استخدام get_chat_history بدلاً من iter_history المتوقفة
        async for message in app.get_chat_history(SOURCE_CHANNEL, limit=200):
            if message.video:
                v_id = str(message.id)
                # تخزين رقم الحلقة في قاعدة البيانات إذا لم تكن موجودة
                db_query("INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO NOTHING", 
                         (v_id, message.caption or f"حلقة {v_id}"), commit=True)
                count += 1
        print(f"✅ تمت المزامنة! تم تفعيل {count} حلقة قديمة بنجاح.")
    except Exception as e:
        print(f"⚠️ فشلت المزامنة: {e}")

# --- التعامل مع الرسائل ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=SOURCE_CHANNEL,
                message_id=int(v_id)
            )
            return
        except Exception:
            await message.reply_text("❌ عذراً، هذا الفيديو غير متوفر حالياً.")
            return

    await message.reply_text("🎬 أهلاً بك يا محمد! البوت يعمل الآن وجاهز لعرض الحلقات.")

# --- تشغيل البوت ---
async def main():
    async with app:
        await fetch_old_videos()  # تشغيل المزامنة عند البداية
        print("🚀 البوت يعمل الآن...")
        await asyncio.Event().wait() # إبقاء البوت يعمل

if __name__ == "__main__":
    asyncio.run(main())
