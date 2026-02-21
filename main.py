from pyrogram import Client, filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

from commands import callback_watch, start_handler
from config import API_HASH, API_ID, BOT_TOKEN, CHANNEL_ID
from handlers import handle_ep_number, handle_poster, handle_quality, handle_video


def create_app() -> Client:
    app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

    # استقبال الفيديو
    app.add_handler(MessageHandler(handle_video, filters.chat(CHANNEL_ID) & (filters.video | filters.document)))

    # استقبال البوستر
    app.add_handler(MessageHandler(handle_poster, filters.chat(CHANNEL_ID) & filters.photo))

    # رقم الحلقة
    app.add_handler(
        MessageHandler(
            handle_ep_number,
            filters.chat(CHANNEL_ID) & filters.text & filters.regex(r"^\d+$") & ~filters.command(["start"]),
        )
    )

    # الجودة
    app.add_handler(
        MessageHandler(
            handle_quality,
            filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]),
        )
    )

    # أوامر البوت
    app.add_handler(MessageHandler(start_handler, filters.command("start") & filters.private))

    # الضغط على أي حلقة
    app.add_handler(CallbackQueryHandler(callback_watch, filters.regex(r"^watch_")))

    return app


def run_bot() -> None:
    app = create_app()
    print("✅ البوت جاهز ويعمل الآن!")
    app.run()


if __name__ == "__main__":
    run_bot()
