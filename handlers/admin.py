# handlers/admin.py
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from database import add_episode, list_episodes

def start(update: Update, context: CallbackContext):
    update.message.reply_text("مرحبًا! أنا بوت الإدارة الخاص بك.")

def add(update: Update, context: CallbackContext):
    """أمر لإضافة حلقة: /add عنوان الرابط"""
    if len(context.args) < 2:
        update.message.reply_text("استخدم: /add <العنوان> <الرابط>")
        return
    title = context.args[0]
    link = context.args[1]
    add_episode(title, link)
    update.message.reply_text(f"تمت إضافة الحلقة: {title}")

def list_all(update: Update, context: CallbackContext):
    episodes = list_episodes()
    if not episodes:
        update.message.reply_text("لا توجد حلقات مخزنة.")
        return
    msg = "\n".join([f"{e['title']}: {e['link']}" for e in episodes])
    update.message.reply_text(msg)
