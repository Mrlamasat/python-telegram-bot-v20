# bot.py
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler
from database import init_db
from handlers import admin

async def main():
    await init_db()
    app = ApplicationBuilder().token("8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0").build()

    # Conversation Handler لإضافة الحلقات
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', admin.start_add)],
        states={
            admin.TITLE: [MessageHandler(filters.VIDEO, admin.receive_video)],
            admin.POSTER: [MessageHandler(filters.PHOTO, admin.receive_poster)],
            admin.EPISODE_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_title)],
            admin.QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_episode_number)],
            admin.CONFIRM: [CallbackQueryHandler(admin.receive_quality)]
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)

    print("البوت يعمل الآن ✅")
    await app.run_polling()

asyncio.run(main())
