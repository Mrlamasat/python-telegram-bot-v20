from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

# الحالات داخل المحادثة
TITLE, EPISODE, QUALITY = range(3)

# قاموس مؤقت لتخزين البيانات لكل مستخدم
pending = {}

# --- دوال المحادثة ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pending[user_id] = {}
    await update.message.reply_text("أهلاً! ارسل عنوان الفيديو:")
    return TITLE

async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    text = update.message.text
    pending[user_id]["title"] = text if text.lower() != "تخطي" else ""

    await update.message.reply_text("🔢 أرسل رقم الحلقة:")
    return EPISODE

async def handle_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["episode"] = int(update.message.text)
    await update.message.reply_text("🎞 اختر الجودة: 1080p / 720p / 480p")
    return QUALITY

async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["quality"] = update.message.text

    data = pending[user_id]

    # مثال لإدخال البيانات في قاعدة البيانات
    from database import DB_PATH
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO videos (video_id, file_id, poster_id, title, episode, quality, duration)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("video_id", "vid123"),  # مثال مؤقت
        data.get("file_id", ""),
        data.get("poster_id", ""),
        data["title"],
        data["episode"],
        data["quality"],
        data.get("duration", "00:00")
    ))
    conn.commit()
    conn.close()

    caption = f"""
{data['title']}
🎬 الحلقة {data['episode']}
✨ {data['quality']}
"""

    keyboard = [
        [InlineKeyboardButton("👍 0", callback_data=f"like_{data.get('video_id','vid123')}")],
        [InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={data.get('video_id','vid123')}")]
    ]

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    del pending[user_id]
    await update.message.reply_text("✅ تم نشر الحلقة بنجاح")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in pending:
        del pending[user_id]
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# --- ConversationHandler ---
admin_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title)],
        EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_episode)],
        QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quality)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)
