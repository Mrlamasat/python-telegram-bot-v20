import os
import psycopg2
from pyrogram import Client, filters

# الإعدادات
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# --- تغيير اسم الجلسة هنا لضمان عدم التداخل مع Termux ---
app = Client("railway_live_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("✅ البوت يعمل الآن بشكل مستقل عن أي جلسات أخرى!")

@app.on_message(filters.command("stats"))
async def stats(client, message):
    try:
        # إضافة timeout للاتصال لكي لا يعلق البوت إذا كانت القاعدة مشغولة
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM videos")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        await message.reply_text(f"📊 القاعدة متصلة. عدد السجلات: {count}")
    except Exception as e:
        await message.reply_text(f"❌ القاعدة لا تستجيب: {e}")

if __name__ == "__main__":
    print("🚀 البوت بدأ التشغيل...")
    app.run()
