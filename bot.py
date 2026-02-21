from handlers import admin, user
from database import init_db

# تهيئة قاعدة البيانات قبل تشغيل البوت
init_db()

from telegram.ext import ApplicationBuilder

# إعدادات البوت
BOT_TOKEN = "YOUR_BOT_TOKEN"

app = ApplicationBuilder().token(BOT_TOKEN).build()

# إضافة Handlers
app.add_handler(admin.admin_conversation_handler)

# تشغيل البوت
app.run_polling()
