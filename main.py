from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
from db import init_db
from handlers import admin, user

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== تهيئة قاعدة البيانات =====
init_db()

# ===== تسجيل المعالجات =====
import asyncio
asyncio.get_event_loop().run_until_complete(admin.register_admin_handlers(app))
asyncio.get_event_loop().run_until_complete(user.register_user_handlers(app))

print("✅ البوت يعمل الآن...")
app.run()
