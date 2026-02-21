from telegram.ext import CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import Update
from database import add_episode
import random

VIDEO, POSTER, TITLE, NUMBER, QUALITY = range(5)

async def start_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل الفيديو الذي تريد رفعه:")
    return VIDEO

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if not video:
        await update.message.reply_text("أرسل فيديو صالح فقط!")
        return VIDEO
    context.user_data["video_file_id"] = video.file_id
    await update.message.reply_text("تم رفع الفيديو! أرسل صورة البوستر الآن...")
    return POSTER

async def handle_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    context.user_data["poster_file_id"] = photo.file_id
    await update.message.reply_text("أرسل عنوان الحلقة (أو اكتب '-' لتخطي):")
    return TITLE

async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["title"] = None if text == "-" else text
    await update.message.reply_text("أرسل رقم الحلقة:")
    return NUMBER

async def handle_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["episode_number"] = int(update.message.text)
    await update.message.reply_text("اختر الجودة: HD أو SD")
    return QUALITY

async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quality = update.message.text.upper()
    if quality not in ["HD", "SD"]:
        await update.message.reply_text("اختر بين HD أو SD فقط")
        return QUALITY
    context.user_data["quality"] = quality
    # إنشاء poster_group عشوائي لتجميع الحلقات بنفس البوستر
    poster_group = str(random.randint(1000, 9999))
    await add_episode(
        video_file_id=context.user_data["video_file_id"],
        poster_file_id=context.user_data["poster_file_id"],
        title=context.user_data.get("title"),
        duration=0,
        quality=context.user_data["quality"],
        poster_group=poster_group
    )
    await update.message.reply_text("تم إضافة الحلقة بنجاح ✅")
    return ConversationHandler.END

def register_handlers(app):
    from telegram.ext import ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", start_admin)],
        states={
            VIDEO: [MessageHandler(filters.VIDEO, handle_video)],
            POSTER: [MessageHandler(filters.PHOTO, handle_poster)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title)],
            NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number)],
            QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quality)],
        },
        fallbacks=[]
    )
    app.add_handler(conv_handler)
