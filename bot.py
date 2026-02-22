from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    
    # إذا كان هناك payload (مثلاً start 123)
    if len(message.command) > 1:
        v_id = message.command[1]

        # جلب الحلقة من قاعدة البيانات
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT v_id, title FROM episodes WHERE v_id=%s", (v_id,))
        episode = cur.fetchone()
        cur.close()
        conn.close()

        if episode:
            try:
                await client.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=CHANNEL_USERNAME,
                    message_id=int(episode["v_id"])
                )
                return
            except Exception as e:
                await message.reply("❌ حدث خطأ أثناء إرسال الحلقة.")
                return

    # الرسالة الافتراضية فقط إذا لا يوجد payload
    await message.reply(
        "🎬 أهلاً بك.\n"
        "أرسل اسم المسلسل للبحث."
    )
