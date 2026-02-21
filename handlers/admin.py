from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from database import execute

PUBLIC_CHANNEL_ID = "@YourChannelUsername"  # ضع اسم قناتك هنا

# الحالات
TITLE, EPISODE, QUALITY = range(3)

# مؤقت لتخزين بيانات المستخدم قبل الحفظ
pending = {}

# البداية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pending[user_id] = {}
    await update.message.reply_text("أهلاً! ارسل عنوان الفيديو:")
    return TITLE

# استقبال العنوان
async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["title"] = update.message.text
    await update.message.reply_text("🔢 أرسل رقم الحلقة:")
    return EPISODE

# استقبال الحلقة
async def handle_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["episode"] = int(update.message.text)
    await update.message.reply_text("🎞 اختر الجودة (1080p / 720p / 480p):")
    return QUALITY

# استقبال الجودة ونشر الفيديو
async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["quality"] = update.message.text
    data = pending[user_id]

    # مثال على بيانات إضافية مؤقتة
    data["video_id"] = "vid_" + str(user_id)
    data["file_id"] = "FILEID123"
    data["poster_id"] = "POSTERID123"
    data["duration"] = "25:00"

    execute("""
    INSERT INTO videos (video_id, file_id, poster_id, title, episode, quality, duration)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data["video_id"], data["file_id"], data["poster_id"],
        data["title"], data["episode"], data["quality"], data["duration"]
    ))

    caption = f"""
{data['title']}
🎬 الحلقة {data['episode']}
⏱ {data['duration']}
✨ {data['quality']}
"""

    keyboard = [
        [InlineKeyboardButton("👍 0", callback_data=f"like_{data['video_id']}")],
        [InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={data['video_id']}")]
    ]

    await context.bot.send_photo(
        chat_id=PUBLIC_CHANNEL_ID,
        photo=data["poster_id"],
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    del pending[user_id]
    await update.message.reply_text("✅ تم نشر الحلقة بنجاح")
    return ConversationHandler.END

# إلغاء العملية
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
    fallbacks=[CommandHandler('cancel', cancel)]
    )
