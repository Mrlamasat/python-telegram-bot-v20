import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# تحميل متغيرات البيئة
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# تعريف الأمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحباً! البوت يعمل 🎉")

# دالة لتشغيل البوت مع إعادة التشغيل التلقائي عند الخطأ
async def main():
    while True:
        try:
            app = ApplicationBuilder().token(TOKEN).build()
            app.add_handler(CommandHandler("start", start))
            print("🔹 البوت شغال الآن...")
            await app.run_polling()
        except Exception as e:
            print(f"❌ خطأ: {e}")
            print("⏳ إعادة التشغيل بعد 5 ثواني...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
