import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- الإعدادات ---
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")

ADMIN_CHANNEL   = "@Ramadan4kTV"
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

app = Client("mo_userbot", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)

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
        print(f"❌ DB Error: {e}")
    finally:
        if conn: conn.close()

# --- وظيفة المزامنة (تصحيح الخطأ هنا) ---
async def sync_old_episodes():
    async with app:
        print("⏳ جاري مزامنة حلقات أمس...")
        count = 0
        # تم تغيير iter_history إلى get_chat_history
        async for msg in app.get_chat_history(ADMIN_CHANNEL, limit=200):
            if msg.video:
                v_id = str(msg.id)
                title = msg.caption or f"حلقة رقم {v_id}"
                db_query("INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO NOTHING", 
                         (v_id, title), commit=True)
                count += 1
        print(f"✅ تمت المزامنة! تم تفعيل {count} حلقة قديمة.")

# --- نظام المشاهدة ---
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=ADMIN_CHANNEL,
                message_id=int(v_id)
            )
            return
        except Exception:
            return await message.reply_text("❌ عذراً، لم أجد الفيديو في القناة المصدرية.")

    await message.reply_text("🎬 أهلاً بك يا محمد.\nتم تفعيل حلقات أمس، يمكنك الآن الضغط على الروابط.")

# --- تشغيل البوت ---
if __name__ == "__main__":
    # تشغيل المزامنة أولاً ثم البوت
    loop = asyncio.get_event_loop()
    loop.run_until_complete(sync_old_episodes())
    print("🚀 البوت يعمل الآن...")
    app.run()
