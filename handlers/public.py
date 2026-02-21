from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from database import get_all_episodes

async def broadcast_episode(context: ContextTypes.DEFAULT_TYPE):
    episodes = await get_all_episodes()
    for ep in episodes:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", callback_data=f"watch_{ep[0]}")]])
        text = f"🎬 الحلقة {ep[0]}\n✨ الجودة: {ep[5]}"
        if ep[3]: text = f"{ep[3]}\n" + text
        await context.bot.send_photo(chat_id=context.bot_data["PUBLIC_CHANNEL"], photo=ep[2], caption=text, reply_markup=kb)

def register_handlers(app):
    pass
