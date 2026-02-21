from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import STORAGE_CHANNEL_ID, PUBLIC_CHANNEL_ID
from database import execute
import uuid

pending = {}

async def handle_video(update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != STORAGE_CHANNEL_ID:
        return

    video = update.message.video or update.message.document
    if not video:
        return

    video_id = str(uuid.uuid4())
    file_id = video.file_id
    duration = f"{video.duration//60}:{video.duration%60:02d}"

    pending[update.message.from_user.id] = {
        "video_id": video_id,
        "file_id": file_id,
        "duration": duration
    }

    await update.message.reply_text("📸 أرسل صورة البوستر")

async def handle_photo(update, context):
    user = update.message.from_user.id
    if user not in pending:
        return

    pending[user]["poster_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("✏️ أرسل عنوان المسلسل (أو اكتب تخطي)")

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
