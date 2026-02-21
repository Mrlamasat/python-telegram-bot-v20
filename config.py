import os

# إعدادات API و البوت
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# القنوات
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0))          # القناة الخاصة بإضافة الحلقات
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "")      # القناة العامة للنشر

# يوزر البوت الجديد (لتحويل الحلقات القديمة)
NEW_BOT_USERNAME = os.environ.get("NEW_BOT_USERNAME", "")
