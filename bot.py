# bot.py
import os
from telegram.ext import ApplicationBuilder, CommandHandler

from handlers import admin

# قراءة التوكن من Environment Variable
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise Exception("ضع BOT_TOKEN في Environment Variables")

app = ApplicationBuilder().token(BOT_TOKEN).build()

# تسجيل الأوامر
app.add_handler(CommandHandler("start", admin.start))
app.add_handler(CommandHandler("add", admin.add))
app.add_handler(CommandHandler("list", admin.list_all))

# تشغيل البوت
print("البوت بدأ العمل...")
app.run_polling()
