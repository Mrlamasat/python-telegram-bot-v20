from pyrogram import Client
from db import init_db
from handlers import register_handlers
from commands import register_commands
from config import API_ID, API_HASH, BOT_TOKEN

init_db()

app = Client("TeleBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

register_handlers(app)
register_commands(app)

print("✅ البوت جاهز للعمل...")
app.run()
