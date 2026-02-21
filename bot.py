from telegram.ext import ApplicationBuilder
from handlers import admin, user
from database import init_db

# تهيئة قاعدة البيانات
init_db()

# إنشاء التطبيق
app = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

# إضافة Handlers
app.add_handler(admin.admin_conversation_handler)

# شغّل البوت
app.run_polling()
