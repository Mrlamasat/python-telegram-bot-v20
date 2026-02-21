# ==============================
# نظام التشغيل المحسّن (حل مشكلة Peer id invalid)
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    param = message.command[1] if len(message.command) > 1 else ""
    if not param: return await message.reply_text(f"أهلاً بك يا محمد 🎬")

    # التحقق من الاشتراك
    try:
        await client.get_chat_member(SUB_CHANNEL, user_id)
    except:
        bot_info = await client.get_me()
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=f"https://t.me/{SUB_CHANNEL.replace('@','')}")], 
                                    [InlineKeyboardButton("🔄 تحقق", url=f"https://t.me/{bot_info.username}?start={param}")]])
        return await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=btn)

    # جلب بيانات الحلقة
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
    
    # محاولة الإنقاذ إذا لم تكن مسجلة
    if not data:
        try:
            # محاولة الوصول للقناة بأكثر من طريقة لتفادي Peer id invalid
            try:
                peer = await client.get_chat(ADMIN_CHANNEL)
                peer_id = peer.id
            except:
                peer_id = int(ADMIN_CHANNEL)

            old_msg = await client.get_messages(peer_id, int(param))
            if old_msg and (old_msg.video or old_msg.document):
                db_query("INSERT INTO episodes (v_id, title, ep_num, quality) VALUES (%s, %s, %s, %s)", (param, "حلقة مؤرشفة", 0, "Original"), commit=True)
                data = {'v_id': param, 'title': 'حلقة مؤرشفة', 'ep_num': 0, 'quality': 'Original', 'poster_uid': None}
        except: pass

    if data:
        buttons = []
        if data.get('poster_uid'):
            related = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_uid=%s ORDER BY ep_num ASC", (data['poster_uid'],), fetchall=True)
            bot_info = await client.get_me()
            row = []
            for ep in related:
                c_id = str(ep['v_id']).strip()
                row.append(InlineKeyboardButton(f"🔹 {ep['ep_num']}" if c_id == param else str(ep['ep_num']), url=f"https://t.me/{bot_info.username}?start={c_id}"))
                if len(row) == 5: buttons.append(row); row = []
            if row: buttons.append(row)

        cap = f"🎬 **{data['title']}**\n⚙️ {data['quality']}"
        try:
            # --- الإصلاح هنا: استخدام المعرف المباشر ---
            # جرب استبدال ADMIN_CHANNEL باليوزر إذا كان للقناة يوزر، مثل "@MyChannel"
            peer_target = int(ADMIN_CHANNEL) 
            
            await client.copy_message(
                chat_id=message.chat.id, 
                from_chat_id=peer_target, 
                message_id=int(data['v_id']), 
                caption=cap,
                reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
            )
        except Exception as e:
            # إذا فشل الرقم، نجرب اليوزر كخيار أخير
            await message.reply_text(f"❌ عذراً محمد، تأكد من إضافة البوت كمسؤول في قناة الأدمن.\nالسبب: {e}")
    else:
        await message.reply_text("❌ لم يتم العثور على هذه الحلقة.")
