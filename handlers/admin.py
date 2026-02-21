from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import sqlite3

DB_PATH = "/app/data/videos.db"
PUBLIC_CHANNEL_ID = "@YourChannelUsername"  # عدل حسب قناتك

# مراحل المحادثة
TITLE, EPISODE, QUALITY = range(3)

# دالة البداية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("أهلاً! أرسل عنوان الحلقة:")
    return TITLE

# دالة حفظ العنوان
async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text
    await update.message.reply_text("🔢 أرسل رقم الحلقة:")
    return EPISODE

# دالة حفظ رقم الحلقة
async def receive_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["episode"] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("يرجى إدخال رقم صحيح للحلقة.")
        return EPISODE
    await update.message.reply_text("🎞 اختر الجودة (1080p / 720p / 480p):")
    return QUALITY

# دالة حفظ الجودة ونشر الحلقة
async def receive_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["quality"] = update.message.text
    data = context.user_data

    # إدخال البيانات في قاعدة البيانات
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO videos (title, episode, quality)
        VALUES (?, ?, ?)
    """, (data["title"], data["episode"], data["quality"]))
    conn.commit()
    conn.close()

    caption = f"""
🎬 {data['title']}
🔢 الحلقة: {data['episode']}
✨ الجودة: {data['quality']}
"""

    # زر مشاهدة الحلقة (يمكن تعديل الرابط)
    keyboard = [
        [InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={data['episode']}")]
    ]

    await update.message.reply_text("✅ تم تسجيل ونشر الحلقة بنجاح!", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data.clear()
    return ConversationHandler.END

# إلغاء المحادثة
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    context.user_data.clear()
    return ConversationHandler.END

# ConversationHandler للإدارة
admin_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
        EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_episode)],
        QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_quality)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)
