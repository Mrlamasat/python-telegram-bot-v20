from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID
import handlers, commands

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# استقبال الفيديوهات
app.add_handler(filters.chat(CHANNEL_ID) & (filters.video | filters.document), handlers.handle_video)
app.add_handler(filters.chat(CHANNEL_ID) & filters.photo, handlers.handle_poster)
app.add_handler(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]), handlers.handle_episode_number)
app.add_handler(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]), handlers.handle_quality)

# أوامر المستخدم
app.add_handler(filters.command("start") & filters.private, commands.start_command)

print("✅ البوت جاهز للعمل...")
app.run()
