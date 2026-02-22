import re
from pyrogram import Client, filters

# أمر سحب الفيديوهات القديمة
@app.on_message(filters.command("import_old") & filters.private)
async def import_old_series(client, message):
    status = await message.reply_text("🔄 جاري سحب جميع الفيديوهات القديمة من القناة...")
    count = 0
    try:
        target_chat = await client.get_chat("Ramadan4kTV")  # ضع معرف القناة أو اسمها

        async for msg in client.get_chat_history(target_chat.id, limit=0):  # limit=0 = كل الرسائل
            # التأكد من أن الرسالة تحتوي فيديو
            if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                continue

            caption = (msg.caption or "").strip()
            title = f"مسلسل بدون اسم {msg.id}"  # اسم افتراضي إذا لم يوجد وصف

            # استخراج رقم الحلقة إن وُجد
            nums = re.findall(r'\d+', caption)
            ep_num = int(nums[0]) if nums else 1

            quality = "1080p"
            if "720" in caption:
                quality = "720p"

            # إدراج المسلسل في جدول series أو استخدام المسلسل الحالي
            existing_series = db_query("SELECT id FROM series WHERE title=%s", (title,), fetchone=True)
            if existing_series:
                series_id = existing_series['id']
            else:
                db_query("INSERT INTO series (title) VALUES (%s)", (title,), commit=True)
                res = db_query("SELECT id FROM series WHERE title=%s", (title,), fetchone=True)
                series_id = res['id'] if res else None

            # إدراج الحلقة في جدول episodes
            if series_id:
                db_query("""
                    INSERT INTO episodes (v_id, series_id, title, ep_num, duration, quality)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (v_id) DO UPDATE SET ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality
                """, (str(msg.id), series_id, title, ep_num, "0:00", quality), commit=True)
                count += 1

            if count % 10 == 0:
                await status.edit_text(f"🔄 جاري العمل.. تم سحب {count} حلقة حتى الآن.")

        await status.edit_text(f"✅ تم الانتهاء! تم سحب {count} حلقة وربطها بالمسلسلات.")
    except Exception as e:
        await status.edit_text(f"❌ حدث خطأ أثناء السحب: {e}")
