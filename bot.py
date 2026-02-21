import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# تحميل متغيرات البيئة
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# تعريف الأمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحباً! البوت يعمل 🎉")

# إنشاء التطبيق
app = ApplicationBuilder().token(TOKEN).build()

# إضافة المعالجات
app.add_handler(CommandHandler("start", start))

# تشغيل البوت
if __name__ == "__main__":
    app.run_polling()
