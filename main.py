from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from handlers import handle_video, handle_poster, handle_ep_number, handle_quality
from commands import start_handler, callback_watch
from config import BOT_TOKEN, CHANNEL_ID

def create_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # استقبال الفيديو
    app.add_handler(MessageHandler(filters.Chat(CHANNEL_ID) & (filters.VIDEO | filters.Document.VIDEO), handle_video))
    # استقبال البوستر
    app.add_handler(MessageHandler(filters.Chat(CHANNEL_ID) & filters.PHOTO, handle_poster))
    # رقم الحلقة
    app.add_handler(MessageHandler(filters.Chat(CHANNEL_ID) & filters.TEXT & filters.Regex(r"^\d+$") & ~filters.COMMAND, handle_ep_number))
    # الجودة
    app.add_handler(MessageHandler(filters.Chat(CHANNEL_ID) & filters.TEXT & ~filters.COMMAND, handle_quality))

    # أوامر البوت
    app.add_handler(CommandHandler("start", start_handler, filters=filters.ChatType.PRIVATE))
    # الضغط على أي حلقة
    app.add_handler(CallbackQueryHandler(callback_watch, pattern=r"^watch_"))

    return app

def run_bot() -> None:
    app = create_app()
    print("✅ البوت جاهز ويعمل الآن!")
    app.run_polling()

if __name__ == "__main__":
    run_bot()
