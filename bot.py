from telegram.ext import ApplicationBuilder
from database import init_db
from handlers import admin

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# إنشاء قاعدة البيانات إذا لم تكن موجودة
init_db()

# إعداد البوت
app = ApplicationBuilder().token(BOT_TOKEN).build()

# إضافة الـ ConversationHandler
app.add_handler(admin.admin_conversation_handler)

print("[INFO] Bot is running...")
app.run_polling()
