# main.py
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
from handlers import register_handlers

# إنشاء نسخة البوت
app = Client(
    "Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# تسجيل جميع معالجات الرسائل والفيديوهات
register_handlers(app)

print("✅ البوت يعمل الآن...")

# تشغيل البوت
app.run()
