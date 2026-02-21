# admin.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

# حالة المحادثة
START, TITLE, EPISODE, QUALITY = range(4)

pending = {}  # لتخزين البيانات مؤقتًا
PUBLIC_CHANNEL_ID = "@your_channel_username"  # عدل حسب القناة

# دالة البداية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pending[user_id] = {}  # تهيئة البيانات
    await update.message.reply_text("أهلاً! ارسل عنوان الفيديو:")
    return TITLE

# دالة لمعالجة العنوان
async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["title"] = update.message.text
    await update.message.reply_text("🔢 أرسل رقم الحلقة")
    return EPISODE

# دالة لمعالجة رقم الحلقة
async def handle_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["episode"] = int(update.message.text)
    await update.message.reply_text("🎞 اختر الجودة: 1080p / 720p / 480p")
    return QUALITY

# دالة لمعالجة الجودة
async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["quality"] = update.message.text
    data = pending[user_id]

    caption = f"""
{data['title']}
🎬 الحلقة {data['episode']}
✨ {data['quality']}
"""

    keyboard = [
        [InlineKeyboardButton("👍 0", callback_data=f"like_{data.get('video_id','0')}")],
        [InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={data.get('video_id','0')}")]
    ]

    await context.bot.send_photo(
        chat_id=PUBLIC_CHANNEL_ID,
        photo=data.get('poster_id', 'https://via.placeholder.com/300'),
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    del pending[user_id]
    await update.message.reply_text("✅ تم نشر الحلقة")
    return ConversationHandler.END

# دالة إلغاء المحادثة
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in pending:
        del pending[user_id]
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# تعريف ConversationHandler
admin_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title)],
        EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_episode)],
        QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quality)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)
