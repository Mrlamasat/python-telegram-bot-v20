import os

# ================= إعدادات API و البوت =================
# إذا لم توجد متغيرات البيئة، سيتم استخدام القيم التالية مؤقتًا
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0")

# ================= القنوات =================
# قناة رفع الحلقات الخاصة (يجب أن يكون البوت مشرف فيها)
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", -1003547072209))

# القناة العامة للنشر (يجب أن يكون البوت مشرف فيها)
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "RamadanSeries26")

# ================= البوت الجديد لتحويل الحلقات القديمة =================
# بدون @
NEW_BOT_USERNAME = os.environ.get("NEW_BOT_USERNAME", "Bottemo_bot")
