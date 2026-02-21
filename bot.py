import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# جلب التوكن من متغير البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("يرجى ضبط متغير البيئة BOT_TOKEN في Railway")

# دالة start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحباً! البوت يعمل 🎉")

# انشاء التطبيق
app = ApplicationBuilder().token(BOT_TOKEN).build()

# إضافة الهاندلر للأمر /start
app.add_handler(CommandHandler("start", start))

# تشغيل البوت
if __name__ == "__main__":
    print("البوت يعمل الآن...")
    app.run_polling()
