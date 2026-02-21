from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from config import BOT_TOKEN
from database import init_db
from handlers import admin, user

init_db()

app = Application.builder().token(BOT_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.VIDEO | filters.Document.VIDEO, admin.start_upload)],
    states={
        admin.POSTER: [MessageHandler(filters.PHOTO, admin.receive_poster)],
        admin.TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_title)],
        admin.EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_episode)],
        admin.QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_quality)],
    },
    fallbacks=[]
)

app.add_handler(conv_handler)
app.add_handler(CommandHandler("start", user.start))
app.add_handler(CallbackQueryHandler(user.watch_callback, pattern="^watch_"))
app.add_handler(CallbackQueryHandler(user.like_callback, pattern="^like_"))

app.run_polling()
