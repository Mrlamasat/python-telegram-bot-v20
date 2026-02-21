import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID"))
PUBLIC_CHANNEL_ID = int(os.getenv("PUBLIC_CHANNEL_ID"))

FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL")  # مثال: @MyChannel

ADMINS = list(map(int, os.getenv("ADMINS").split(",")))
