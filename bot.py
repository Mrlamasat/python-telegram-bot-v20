import os
from telegram.ext import ApplicationBuilder, CommandHandler

from handlers import admin  # استيراد دوال الأوامر

# ============================
# Environment Variables
# ============================
BOT_TOKEN = os.environ.get("BOT_TOKEN")           # توكن البوت
CHANNEL_ID = os.environ.get("CHANNEL_ID")         # معرف القناة @اسم_القناة أو رقم معرف القناة
DATABASE_FILE = os.environ.get("DATABASE_FILE", "episodes.db")  # اسم قاعدة البيانات

if not BOT_TOKEN:
    raise Exception("ضع BOT_TOKEN في Environment Variables")

# إنشاء التطبيق
app = ApplicationBuilder().token(BOT_TOKEN).build()

# تسجيل الأوامر
app.add_handler(CommandHandler("start", admin.start))
app.add_handler(CommandHandler("add", admin.add))
app.add_handler(CommandHandler("list", admin.list_all))

print("البوت بدأ العمل...")
app.run_polling()
