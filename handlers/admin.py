from telegram import Update
from telegram.ext import ContextTypes
from database import add_episode, list_episodes
import os

CHANNEL_ID = os.environ.get("CHANNEL_ID")

# ======== أمر /start ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحبًا! أنا بوت الإدارة الخاص بك.\n"
        "الأوامر المتاحة:\n"
        "/add <العنوان> <الرابط>\n"
        "/list"
    )

# ======== أمر /add ========
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("استخدم: /add <العنوان> <الرابط>")
        return

    title = context.args[0]
    link = context.args[1]

    # إضافة الحلقة للـ database
    add_episode(title, link)

    # إرسال الحلقة للقناة إذا معرف القناة موجود
    if CHANNEL_ID:
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=f"{title}\n{link}")
        except Exception as e:
            await update.message.reply_text(f"تمت إضافة الحلقة لكن فشل الإرسال للقناة: {e}")
            return

    await update.message.reply_text(f"تمت إضافة الحلقة: {title}")

# ======== أمر /list ========
async def list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    episodes = list_episodes()
    if not episodes:
        await update.message.reply_text("لا توجد حلقات مخزنة.")
        return

    msg = "\n".join([f"{e['title']}: {e['link']}" for e in episodes])
    await update.message.reply_text(msg)
