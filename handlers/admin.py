# handlers/admin.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
from database import add_episode

TITLE, POSTER, EPISODE_NUM, QUALITY, CONFIRM = range(5)

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل رابط/ملف الفيديو للحلقة:")
    return TITLE

async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['video_file_id'] = update.message.video.file_id
    await update.message.reply_text("أرسل صورة البوستر:")
    return POSTER

async def receive_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['poster'] = update.message.photo[-1].file_id
    await update.message.reply_text("أرسل عنوان الحلقة:")
    return EPISODE_NUM

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['title'] = update.message.text
    await update.message.reply_text("أرسل رقم الحلقة:")
    return QUALITY

async def receive_episode_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['episode_number'] = int(update.message.text)
    keyboard = [
        [InlineKeyboardButton("1080p", callback_data="1080p"),
         InlineKeyboardButton("720p", callback_data="720p")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر الجودة:", reply_markup=reply_markup)
    return CONFIRM

async def receive_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['quality'] = query.data

    data = context.user_data
    await add_episode(
        data['title'], data['poster'], data['video_file_id'],
        data['quality'], data['episode_number']
    )
    await query.edit_message_text(f"تم إضافة الحلقة: {data['title']} ✅")
    return ConversationHandler.END

from telegram.ext import CallbackQueryHandler
