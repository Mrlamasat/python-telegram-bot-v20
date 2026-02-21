from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database import execute
from config import FORCE_SUB_CHANNEL
from telegram.ext import ContextTypes

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("أرسل رابط الحلقة")
        return

    video_id = context.args[0]

    member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, update.effective_user.id)
    if member.status in ["left", "kicked"]:
        await update.message.reply_text(
            f"🔒 اشترك أولاً في @{FORCE_SUB_CHANNEL}"
        )
        return

    video = execute("SELECT * FROM videos WHERE video_id=?", (video_id,), True)
    if not video:
        await update.message.reply_text("الحلقة غير موجودة")
        return

    video = video[0]

    await update.message.reply_video(video=video[1])

    episodes = execute(
        "SELECT video_id, episode FROM videos WHERE poster_id=? ORDER BY episode",
        (video[2],),
        True
    )

    buttons = []
    row = []
    for v_id, ep in episodes:
        row.append(InlineKeyboardButton(str(ep), callback_data=f"watch_{v_id}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await update.message.reply_text(
        "شاهد المزيد من الحلقات",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def watch_callback(update, context):
    query = update.callback_query
    await query.answer()

    video_id = query.data.split("_")[1]

    video = execute("SELECT file_id FROM videos WHERE video_id=?", (video_id,), True)
    if video:
        await query.message.reply_video(video=video[0][0])
