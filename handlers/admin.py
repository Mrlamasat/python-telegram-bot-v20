# admin.py

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

# حالة بداية المحادثة
START, TITLE = range(2)

# دالة البداية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً! ارسل عنوانك:")
    return TITLE

# دالة لمعالجة العنوان
async def handle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    title_text = update.message.text

    # هنا ممكن تعمل أي عملية تريدها بالعنوان و user_id
    await update.message.reply_text(f"تم تسجيل العنوان: {title_text} للمستخدم: {user_id}")

    # إنهاء المحادثة
    return ConversationHandler.END

# دالة إلغاء المحادثة
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# تعريف ConversationHandler
from telegram.ext import CommandHandler, MessageHandler, filters

admin_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)        context.user_data["title"] = ""

    await update.message.reply_text("🔢 أرسل رقم الحلقة")
    return EPISODE


async def receive_episode(update, context):
    context.user_data["episode"] = int(update.message.text)
    await update.message.reply_text("🎞 اختر الجودة (1080p / 720p / 480p)")
    return QUALITY


async def receive_quality(update, context):
    context.user_data["quality"] = update.message.text

    data = context.user_data

    db("""
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

    await update.message.reply_text("✅ تم نشر الحلقة بنجاح")
    context.user_data.clear()
    return ConversationHandler.END 
    async def handle_title(update, context):
    user = update.message.from_user.id
    if user not in pending:
        return

    if update.message.text.lower() != "تخطي":
        pending[user]["title"] = update.message.text
    else:
        pending[user]["title"] = ""

    await update.message.reply_text("🔢 أرسل رقم الحلقة")

async def handle_episode(update, context):
    user = update.message.from_user.id
    if user not in pending:
        return

    pending[user]["episode"] = int(update.message.text)
    await update.message.reply_text("🎞 اختر الجودة: 1080p / 720p / 480p")

async def handle_quality(update, context):
    user = update.message.from_user.id
    if user not in pending:
        return

    pending[user]["quality"] = update.message.text

    data = pending[user]

    execute("""
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

    caption = f"""
🎬 الحلقة {data['episode']}
⏱ {data['duration']}
✨ {data['quality']}
"""

    keyboard = [
        [
            InlineKeyboardButton("👍 0", callback_data=f"like_{data['video_id']}")
        ],
        [
            InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={data['video_id']}")
        ]
    ]

    await context.bot.send_photo(
        chat_id=PUBLIC_CHANNEL_ID,
        photo=data["poster_id"],
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    del pending[user]
    await update.message.reply_text("✅ تم نشر الحلقة")
