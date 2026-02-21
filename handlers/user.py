# يمكنك إضافة هنا أوامر المستخدم العادية
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("هذا البوت لإدارة الفيديوهات. استخدم /start للنشر.")

# يمكنك تسجيل الـ handlers في bot.py إذا أردت
