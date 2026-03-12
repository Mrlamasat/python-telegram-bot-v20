import os

# ===== إعدادات البوت =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8619590433:AAFhbBbIdA4tGYpmn9gCwKv6TvZs4BbkSzM")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway")

# ===== القنوات =====
SOURCE_CHANNEL = int(os.environ.get("SOURCE_CHANNEL", "-1003547072209"))
PUBLISH_CHANNEL = int(os.environ.get("PUBLISH_CHANNEL", "-1003689965691"))
FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "-1003637472584"))

# ===== الإعدادات الثابتة =====
ADMIN_ID = 7720165591
FORCE_SUB_LINK = "https://t.me/+bJVu0tEtj9UyMmFk"  # رابط القناة الإجبارية (والاحتياطية)

# ===== التحكم في المزيد من الحلقات =====
SHOW_MORE_BUTTONS = True

# ===== نظام الحماية من FloodWait =====
REQUEST_LIMIT = 5
TIME_WINDOW = 10

# ===== كلمات التشفير =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد"]
