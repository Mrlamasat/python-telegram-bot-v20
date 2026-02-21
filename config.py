import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID"))
PUBLIC_CHANNEL_ID = os.getenv("PUBLIC_CHANNEL_ID")
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL")
ADMINS = list(map(int, os.getenv("ADMINS").split(",")))
DB_PATH = os.getenv("DB_PATH", "bot_data.db")
