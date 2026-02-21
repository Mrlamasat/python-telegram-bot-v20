from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ConversationHandler, MessageHandler, filters
from config import STORAGE_CHANNEL_ID, PUBLIC_CHANNEL_ID
from database import db
import uuid

VIDEO, POSTER, TITLE, EPISODE, QUALITY = range(5)

async def start_upload(update, context):
    if update.effective_chat.id != STORAGE_CHANNEL_ID:
        return ConversationHandler.END

    video = update.message.video or update.message.document
    if not video:
        return ConversationHandler.END

    context.user_data.clear()

    context.user_data["video_id"] = str(uuid.uuid4())
    context.user_data["file_id"] = video.file_id
    context.user_data["duration"] = f"{video.duration//60}:{video.duration%60:02d}"

    await update.message.reply_text("📸 أرسل صورة البوستر")
    return POSTER


async def receive_poster(update, context):
    context.user_data["poster_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("✏️ أرسل عنوان المسلسل (أو اكتب تخطي)")
    return TITLE


async def receive_title(update, context):
    if update.message.text.lower() != "تخطي":
        context.user_data["title"] = update.message.text
    else:
        context.user_data["title"] = ""

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
