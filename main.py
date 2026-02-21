from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID
from handlers import handle_video, handle_poster, handle_ep_number, handle_quality
from commands import start_handler, callback_watch

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# استقبال الفيديو
@app.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def video_msg(client, message):
    await handle_video(client, message)

# استقبال البوستر (صورة)
@app.on_message(filters.chat(CHANNEL_ID) & filters.photo)
async def poster_msg(client, message):
    await handle_poster(client, message)

# استقبال رقم الحلقة
@app.on_message(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]))
async def ep_number_msg(client, message):
    res = await handle_ep_number(client, message)
    await handle_quality(client, message)

# أوامر البوت
@app.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    await start_handler(client, message)

# الضغط على أزرار الحلقات
@app.on_callback_query(filters.regex(r"^watch_"))
async def callback(client, query):
    await callback_watch(client, query)

print("✅ البوت يعمل الآن...")
app.run()
