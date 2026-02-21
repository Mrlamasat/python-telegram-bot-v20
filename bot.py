from telegram.ext import ApplicationBuilder
from handlers import admin
from database import init_db

# إنشاء قاعدة البيانات قبل تشغيل البوت
init_db()

BOT_TOKEN = "YOUR_BOT_TOKEN"  # غيره بالتوكن الحقيقي

app = ApplicationBuilder().token(BOT_TOKEN).build()

# إضافة ConversationHandler
app.add_handler(admin.admin_conversation_handler)

# تشغيل البوت
app.run_polling()
