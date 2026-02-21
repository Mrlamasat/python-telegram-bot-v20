async def like_callback(update, context):
    query = update.callback_query
    await query.answer()

    video_id = query.data.split("_")[1]
    user_id = query.from_user.id

    try:
        execute("INSERT INTO likes VALUES (?, ?)", (video_id, user_id))
    except:
        return

    count = execute("SELECT COUNT(*) FROM likes WHERE video_id=?", (video_id,), True)[0][0]

    keyboard = [
        [
            InlineKeyboardButton(f"👍 {count}", callback_data=f"like_{video_id}")
        ],
        [
            InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{context.bot.username}?start={video_id}")
        ]
    ]

    await query.message.edit_reply_markup(InlineKeyboardMarkup(keyboard))
