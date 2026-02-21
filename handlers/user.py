from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from config import FORCE_SUB_CHANNEL


async def start(update, context):
    if not context.args:
        await update.message.reply_text("أرسل رابط الحلقة.")
        return

    video_id = context.args[0]

    member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, update.effective_user.id)
    if member.status in ["left", "kicked"]:
        await update.message.reply_text(f"🔒 اشترك أولاً في {FORCE_SUB_CHANNEL}")
        return

    video = db("SELECT * FROM videos WHERE video_id=?", (video_id,), True)
    if not video:
        await update.message.reply_text("الحلقة غير موجودة.")
        return

    video = video[0]

    await update.message.reply_video(video=video[1])

    episodes = db(
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
        "📺 شاهد المزيد من الحلقات",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def watch_callback(update, context):
    query = update.callback_query
    await query.answer()

    video_id = query.data.split("_")[1]

    video = db("SELECT file_id FROM videos WHERE video_id=?", (video_id,), True)
    if video:
        await query.message.reply_video(video=video[0][0])


async def like_callback(update, context):
    query = update.callback_query
    await query.answer()

    video_id = query.data.split("_")[1]
    user_id = query.from_user.id

    try:
        db("INSERT INTO likes VALUES (?, ?)", (video_id, user_id))
    except:
        return

    count = db("SELECT COUNT(*) FROM likes WHERE video_id=?", (video_id,), True)[0][0]

    keyboard = [
        [InlineKeyboardButton(f"👍 {count}", callback_data=f"like_{video_id}")],
        [InlineKeyboardButton("▶️ مشاهدة الحلقة",
         url=f"https://t.me/{context.bot.username}?start={video_id}")]
    ]

    await query.message.edit_reply_markup(InlineKeyboardMarkup(keyboard))
