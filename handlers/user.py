# handlers/user.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, ConversationHandler, filters

# مراحل المحادثة
EPISODE, QUALITY = range(2)

# قاموس لتخزين بيانات مؤقتة لكل مستخدم
pending = {}

# دالة البداية
async def start_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pending[user_id] = {}
    await update.message.reply_text("🔢 أرسل رقم الحلقة:")
    return EPISODE

# استقبال رقم الحلقة
async def receive_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    try:
        pending[user_id]["episode"] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("⚠️ يجب أن يكون رقم الحلقة رقماً صحيحاً. حاول مرة أخرى:")
        return EPISODE

    await update.message.reply_text("🎞 اختر الجودة: 1080p / 720p / 480p")
    return QUALITY

# استقبال الجودة
async def receive_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in pending:
        return ConversationHandler.END

    quality = update.message.text.lower()
    if quality not in ["1080p", "720p", "480p"]:
        await update.message.reply_text("⚠️ الجودة غير صالحة. اختر: 1080p / 720p / 480p")
        return QUALITY

    pending[user_id]["quality"] = quality

    # هنا يمكنك إضافة أي عملية أخرى مثل حفظ البيانات في قاعدة البيانات
    # مثال: نشر الحلقة أو إرسالها للقناة
    await update.message.reply_text(
        f"✅ تم تسجيل الحلقة {pending[user_id]['episode']} بجودة {pending[user_id]['quality']}"
    )

    # تنظيف البيانات المؤقتة
    del pending[user_id]
    return ConversationHandler.END

# دالة الإلغاء
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in pending:
        del pending[user_id]
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# تعريف ConversationHandler
user_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start_user)],
    states={
        EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_episode)],
        QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_quality)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
