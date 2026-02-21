# bot.py

import os
from telegram.ext import ApplicationBuilder, CommandHandler
from handlers import admin

# قراءة التوكن من المتغير البيئي
BOT_TOKEN = os.getenv("BOT_TOKEN")  # ضع هذا المتغير في إعدادات Railway

async def start(update, context):
    await update.message.reply_text("أهلاً! البوت جاهز للعمل.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # إضافة الهاندلرز
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_episode", admin.add_episode_handler))

    print("البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
