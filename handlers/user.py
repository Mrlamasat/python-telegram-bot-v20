from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
import sqlite3

DB_PATH = "/app/data/videos.db"

# أمر عرض آخر الحلقات
async def latest_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # جلب آخر 5 حلقات
    cursor.execute("SELECT id, title, episode, quality FROM videos ORDER BY id DESC LIMIT 5")
    videos = cursor.fetchall()
    conn.close()

    if not videos:
        await update.message.reply_text("لا توجد حلقات حالياً.")
        return

    for vid in videos:
        vid_id, title, episode, quality = vid
        caption = f"🎬 {title}\n🔢 الحلقة: {episode}\n✨ الجودة: {quality}"
        keyboard = [
            [InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={episode}")]
        ]
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard))

# CommandHandler جاهز للإضافة في التطبيق الرئيسي
user_command_handler = CommandHandler('latest', latest_videos)
