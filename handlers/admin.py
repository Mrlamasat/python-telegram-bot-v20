from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from database import add_episode, list_episodes
import os

# أخذ إعدادات من البيئة
CHANNEL_ID = os.getenv("RamadanSeries26")  # مثال: -1001234567890

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحبًا! أنا بوت الإدارة الخاص بك.\n"
        "الأوامر المتاحة:\n"
        "/add <العنوان> <الرابط>\n"
        "/list"
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("الرجاء استخدام الصيغة: /add <العنوان> <الرابط>")
        return

    title = " ".join(args[:-1])
    link = args[-1]

    add_episode(title, link)

    if CHANNEL_ID:
        await context.bot.send_message(CHANNEL_ID, f"{title}: {link}")

    await update.message.reply_text(f"تمت إضافة الحلقة: {title}")

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    episodes = list_episodes()
    if not episodes:
        await update.message.reply_text("لا توجد حلقات مضافة حتى الآن.")
        return

    msg = "\n".join([f"{title}: {link}" for title, link in episodes])
    await update.message.reply_text(msg)
