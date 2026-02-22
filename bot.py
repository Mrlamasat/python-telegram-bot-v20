import os
import asyncio
import psycopg2
from pyrogram import Client, filters

# --- الإعدادات ---
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")
SOURCE_CHANNEL = "@Ramadan4kTV"

app = Client("my_bot", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)

# --- دالة قاعدة البيانات ---
def save_to_db(v_id, title):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute("INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO NOTHING", (v_id, title))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ DB Error: {e}")

# --- المزامنة (الإصدار المصحح 100%) ---
async def sync_episodes():
    print("⏳ جاري سحب حلقات أمس...")
    async with app:
        # هنا استخدمنا get_chat_history وهي الدالة الصحيحة حالياً
        async for message in app.get_chat_history(SOURCE_CHANNEL, limit=100):
            if message.video:
                v_id = str(message.id)
                caption = message.caption or f"حلقة {v_id}"
                save_to_db(v_id, caption)
        print("✅ اكتملت المزامنة بنجاح!")

# --- استقبال الأوامر ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) > 1:
        v_id = int(message.command[1])
        try:
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, v_id)
        except:
            await message.reply_text("❌ لم أتمكن من إرسال هذا الفيديو.")
    else:
        await message.reply_text("🎬 أهلاً بك يا محمد، البوت يعمل الآن.")

# --- التشغيل الرئيسي ---
async def main():
    await sync_episodes()
    print("🚀 البوت يعمل الآن...")
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
