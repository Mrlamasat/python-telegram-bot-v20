# admin.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, ConversationHandler, filters
from database import init_db, DB_PATH
import sqlite3

# حالات المحادثة
TITLE, EPISODE, QUALITY = range(3)

# تخزين مؤقت للمستخدمين
pending = {}

PUBLIC_CHANNEL_ID = "@YourChannelUsername"  # غيره بالمعرف الفعلي

# البداية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pending[user_id] = {}
    await update.message.reply_text("أهلاً! ارسل عنوان الحلقة:")
    return TITLE

# استقبال العنوان
async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if user not in pending:
        return ConversationHandler.END

    pending[user]["title"] = update.message.text
    await update.message.reply_text("🔢 أرسل رقم الحلقة:")
    return EPISODE

# استقبال رقم الحلقة
async def handle_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if user not in pending:
        return ConversationHandler.END

    pending[user]["episode"] = int(update.message.text)
    await update.message.reply_text("🎞 اختر الجودة: 1080p / 720p / 480p")
    return QUALITY

# استقبال الجودة ونشر الحلقة
async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if user not in pending:
        return ConversationHandler.END

    data = pending[user]
    data["quality"] = update.message.text

    # إدخال البيانات في قاعدة البيانات
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO videos (video_id, file_id, poster_id, title, episode, quality, duration)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("video_id", "vid123"),
        data.get("file_id", "file123"),
        data.get("poster_id", "poster123"),
        data["title"],
        data["episode"],
        data["quality"],
        data.get("duration", "00:25:00")
    ))
    conn.commit()
    conn.close()

    caption = f"""
🎬 {data['title']}
🎞 الحلقة {data['episode']}
✨ الجودة: {data['quality']}
⏱ المدة: {data.get('duration', 'غير محددة')}
"""
    keyboard = [
        [InlineKeyboardButton("👍 0", callback_data=f"like_{data.get('video_id', 'vid123')}")],
        [InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={data.get('video_id', 'vid123')}")]
    ]

    await context.bot.send_message(chat_id=PUBLIC_CHANNEL_ID, text=caption, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ تم نشر الحلقة بنجاح")
    del pending[user]
    return ConversationHandler.END

# إلغاء المحادثة
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    if user in pending:
        del pending[user]
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
