# bot.py
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# دالة الرد على /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحبًا! البوت يعمل بنجاح ✅")

# هنا تبني التطبيق باستخدام توكن البوت
if __name__ == "__main__":
    app = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

    # إضافة الهاندلر لأمر /start
    app.add_handler(CommandHandler("start", start))

    # تشغيل البوت بالـ polling
    app.run_polling()
