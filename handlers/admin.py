# admin.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

# الحالات
START, TITLE, EPISODE, QUALITY = range(4)

# قاموس لتخزين بيانات مؤقتة
pending = {}

# دالة البداية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pending[user_id] = {}  # انشاء مكان لتخزين البيانات مؤقتًا
    await update.message.reply_text("أهلاً! ارسل عنوان الفيديو:")
    return TITLE

# معالجة العنوان
async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    text = update.message.text
    if text.lower() != "تخطي":
        pending[user_id]["title"] = text
    else:
        pending[user_id]["title"] = ""

    await update.message.reply_text("🔢 أرسل رقم الحلقة:")
    return EPISODE

# معالجة رقم الحلقة
async def handle_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["episode"] = int(update.message.text)
    await update.message.reply_text("🎞 اختر الجودة: 1080p / 720p / 480p")
    return QUALITY

# معالجة الجودة ونشر الفيديو
async def handle_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    pending[user_id]["quality"] = update.message.text
    data = pending[user_id]

    # تخزين البيانات في قاعدة البيانات
    # لاحظ: يجب تعريف دالة execute أو الاتصال بقاعدة البيانات
    execute("""
        INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("video_id"),
        data.get("file_id"),
        data.get("poster_id"),
        data.get("title"),
        data.get("episode"),
        data.get("quality"),
        data.get("duration")
    ))

    # إعداد الكابتشن
    caption = f"""
🎬 الحلقة {data.get('episode')}
⏱ {data.get('duration')}
✨ {data.get('quality')}
"""

    # إعداد لوحة الأزرار
    keyboard = [
        [InlineKeyboardButton("👍 0", callback_data=f"like_{data.get('video_id')}")],
        [InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={data.get('video_id')}")]
    ]

    # إرسال الصورة مع الكابتشن
    await context.bot.send_photo(
        chat_id=PUBLIC_CHANNEL_ID,
        photo=data.get("poster_id"),
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    del pending[user_id]  # حذف البيانات المؤقتة
    await update.message.reply_text("✅ تم نشر الحلقة بنجاح")
    return ConversationHandler.END

# دالة الإلغاء
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in pending:
        del pending[user_id]

    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# تعريف الـ ConversationHandler
admin_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title)],
        EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_episode)],
        QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quality)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)
