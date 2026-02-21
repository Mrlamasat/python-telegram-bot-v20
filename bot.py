from telegram.ext import ApplicationBuilder, CommandHandler
from handlers.admin import start, add, list_cmd
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

app = ApplicationBuilder().token(BOT_TOKEN).build()

# تسجيل الأوامر
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("list", list_cmd))

print("البوت يعمل الآن...")

app.run_polling()
