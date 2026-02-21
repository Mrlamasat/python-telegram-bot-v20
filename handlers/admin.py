from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from database import DB_PATH
import sqlite3
import os

START, TITLE, EPISODE, QUALITY = range(4)
PUBLIC_CHANNEL_ID = "@YourChannelUsername"  # عدّل على حسب قناتك

# محفظة مؤقتة لتخزين البيانات قبل الإضافة للقاعدة
pending = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pending[user_id] = {}
    await update.message.reply_text("أهلاً! ارسل عنوان الحلقة:")
    return TITLE

async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if user not in pending:
        return ConversationHandler.END

    pending[user]["title"] = update.message.text
    await update.message.reply_text("🔢 أرسل رقم الحلقة:")
    return EPISODE

async def handle_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if user not in pending:
        return ConversationHandler.END

    pending[user]["episode"] = int(update.message.text)
    await update.message.reply_text("🎞 اختر الجودة (1080p / 720p / 480p):")
    return QUALITY

async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if user not in pending:
        return ConversationHandler.END

    pending[user]["quality"] = update.message.text

    data = pending[user]
    data["video_id"] = str(user) + "_" + str(data["episode"])  # مثال لتوليد ID
    data["file_id"] = "FILE_ID_PLACEHOLDER"
    data["poster_id"] = "POSTER_ID_PLACEHOLDER"
    data["duration"] = "00:20:00"

    # إضافة للقاعدة
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data["video_id"],
        data["file_id"],
        data["poster_id"],
        data["title"],
        data["episode"],
        data["quality"],
        data["duration"]
    ))
    conn.commit()
    conn.close()

    caption = f"""
{data['title']}
🎬 الحلقة {data['episode']}
⏱ {data['duration']}
✨ {data['quality']}
"""

    keyboard = [
        [InlineKeyboardButton("👍 0", callback_data=f"like_{data['video_id']}")],
        [InlineKeyboardButton("▶️ مشاهدة الحلقة",
         url=f"https://t.me/{context.bot.username}?start={data['video_id']}")]
    ]

    await context.bot.send_photo(
        chat_id=PUBLIC_CHANNEL_ID,
        photo=data["poster_id"],
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    del pending[user]
    await update.message.reply_text("✅ تم نشر الحلقة بنجاح")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

admin_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title)],
        EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_episode)],
        QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quality)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)
