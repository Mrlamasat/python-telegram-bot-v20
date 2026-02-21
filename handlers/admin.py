# handlers/admin.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters

from database import add_episode  # تأكد أن دالة add_episode موجودة في database.py

# الحالات في المحادثة
VIDEO, POSTER, TITLE, EPISODE_NUM, QUALITY, CONFIRM = range(6)

async def start_add_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 ارسل الفيديو للحلقة:")
    return VIDEO

async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.video:
        await update.message.reply_text("❌ الرجاء ارسال ملف فيديو صالح!")
        return VIDEO
    context.user_data['video_file_id'] = update.message.video.file_id
    await update.message.reply_text("🖼 الآن ارسل صورة البوستر للحلقة:")
    return POSTER

async def receive_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ الرجاء ارسال صورة صالحة!")
        return POSTER
    context.user_data['poster'] = update.message.photo[-1].file_id
    await update.message.reply_text("✏️ ارسل عنوان الحلقة:")
    return TITLE

async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        await update.message.reply_text("❌ الرجاء ارسال نص صالح للعنوان!")
        return TITLE
    context.user_data['title'] = text
    await update.message.reply_text("🔢 ارسل رقم الحلقة:")
    return EPISODE_NUM

async def receive_episode_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit():
        await update.message.reply_text("❌ الرجاء ارسال رقم الحلقة بصيغة رقمية!")
        return EPISODE_NUM
    context.user_data['episode_number'] = int(text)

    # عرض أزرار اختيار الجودة
    keyboard = [
        [InlineKeyboardButton("HD", callback_data="HD"),
         InlineKeyboardButton("SD", callback_data="SD")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚡ اختر جودة الفيديو:", reply_markup=reply_markup)
    return CONFIRM

async def receive_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['quality'] = query.data

    # تحقق من جميع الحقول قبل الإضافة
    data = context.user_data
    required_keys = ['title', 'poster', 'video_file_id', 'quality', 'episode_number']
    for key in required_keys:
        if key not in data:
            await query.edit_message_text(f"❌ خطأ: {key} غير موجود!")
            return ConversationHandler.END

    # إضافة الحلقة إلى قاعدة البيانات
    await add_episode(
        title=data['title'],
        poster=data['poster'],
        video_file_id=data['video_file_id'],
        quality=data['quality'],
        episode_number=data['episode_number']
    )

    await query.edit_message_text(f"✅ تم إضافة الحلقة: {data['title']}")
    context.user_data.clear()  # مسح البيانات بعد الإضافة
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء إضافة الحلقة.")
    context.user_data.clear()
    return ConversationHandler.END

# ConversationHandler للإضافة
add_episode_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, start_add_episode)],
    states={
        VIDEO: [MessageHandler(filters.VIDEO, receive_video)],
        POSTER: [MessageHandler(filters.PHOTO, receive_poster)],
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
        EPISODE_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_episode_number)],
        CONFIRM: [CallbackQueryHandler(receive_quality)]
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel)]
    )
