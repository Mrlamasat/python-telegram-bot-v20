from telegram.ext import CallbackQueryHandler, ContextTypes
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_all_episodes

async def watch_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ep_id = int(query.data.split("_")[1])
    episodes = await get_all_episodes()
    ep = next((e for e in episodes if e[0]==ep_id), None)
    if ep:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("مشاهدة المزيد", callback_data="more")]])
        await query.message.reply_video(ep[1], caption=f"🎬 الحلقة {ep[0]}\n✨ الجودة: {ep[5]}", reply_markup=kb)

def register_handlers(app):
    app.add_handler(CallbackQueryHandler(watch_episode, pattern=r"watch_\d+"))
