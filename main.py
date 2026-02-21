from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
import handlers      # استيراد استقبال الفيديو والبوستر
import commands      # استيراد الأوامر

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

print("✅ بوت تيليجرام جاهز للعمل...")
app.run()
