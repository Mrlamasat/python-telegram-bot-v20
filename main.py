from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID
from handlers import handle_video, handle_poster, handle_ep_number, handle_quality
from commands import start_handler, callback_watch

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# استقبال الفيديو
app.add_handler(filters.chat(CHANNEL_ID) & (filters.video | filters.document), handle_video)

# استقبال البوستر
app.add_handler(filters.chat(CHANNEL_ID) & filters.photo, handle_poster)

# رقم الحلقة
app.add_handler(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]), handle_ep_number)

# الجودة
app.add_handler(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]), handle_quality)

# أوامر البوت
app.add_handler(filters.command("start") & filters.private, start_handler)

# الضغط على أي حلقة
app.add_handler(filters.callback_query(filters.regex(r"^watch_")), callback_watch)

print("✅ البوت جاهز ويعمل الآن!")
app.run()
