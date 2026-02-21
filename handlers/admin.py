from telegram.ext import MessageHandler, filters, ContextTypes
from telegram import Update

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if not video:
        await update.message.reply_text("أرسل فيديو صالح فقط!")
        return

    file_path = f"downloads/{video.file_id}.mp4"
    await video.get_file().download_to_drive(file_path)
    await update.message.reply_text("تم رفع الفيديو! أرسل صورة البوستر الآن...")
    context.user_data["video_file"] = video.file_id
