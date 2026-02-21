from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID
import handlers, commands

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# استقبال الفيديوهات
app.add_handler(filters.chat(CHANNEL_ID) & (filters.video | filters.document), handlers.handle_video)
# استقبال البوستر
app.add_handler(filters.chat(CHANNEL_ID) & filters.photo, handlers.handle_poster)
# استقبال رقم الحلقة
app.add_handler(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]), handlers.handle_ep_number)
# أوامر المستخدم
app.add_handler(filters.command("start") & filters.private, commands.start_handler)
# الضغط على زر الحلقات
app.add_handler(filters.callback_query(filters.regex(r"^watch_")), commands.watch_callback)

print("✅ البوت يعمل الآن...")
app.run()
