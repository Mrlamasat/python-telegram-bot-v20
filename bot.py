@bot_app.on_message(filters.command("import_updated") & filters.private)
async def import_updated_series(client, message):
    status = await message.reply_text("🔄 جاري السحب ومعالجة البيانات...")
    count = 0
    try:
        if not user_app.is_connected:
            await user_app.start()

        target_chat = await user_app.get_chat(ADMIN_CHANNEL)
        
        async for msg in user_app.get_chat_history(target_chat.id):
            # فحص الفيديو
            is_video = msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)
            
            if is_video:
                # تأمين النص: إذا كان الـ Caption فارغاً نحوله لنص فارغ "" بدلاً من None
                caption = (msg.caption or "").strip()
                media_info = msg.video or msg.document
                file_name = getattr(media_info, "file_name", "") or ""

                # 1. تحديد الاسم
                if caption:
                    clean_title = caption.split('\n')[0].replace('🎬', '').strip()
                else:
                    clean_title = file_name if file_name else "مسلسل غير معروف"

                # 2. استخراج رقم الحلقة (التأمين من الخطأ هنا)
                # ندمج النصين معاً لضمان وجود شيء للفحص
                text_to_search = f"{caption} {file_name}"
                nums = re.findall(r'\d+', text_to_search)
                ep_num = int(nums[0]) if nums else 1

                # 3. حفظ البيانات
                db_query("INSERT INTO series (title) VALUES (%s) ON CONFLICT (title) DO NOTHING", (clean_title,), commit=True)
                s_res = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                
                if s_res:
                    db_query("""
                        INSERT INTO episodes (v_id, series_id, title, ep_num, quality)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num
                    """, (str(msg.id), s_res['id'], clean_title, ep_num, "1080p"), commit=True)
                    count += 1
                    if count % 20 == 0:
                        await status.edit_text(f"🔄 جاري السحب.. تم العثور على {count} حلقة.")

        await status.edit_text(f"✅ اكتمل السحب بنجاح!\n📦 تم تسجيل {count} حلقة.")
    except Exception as e:
        print(f"Detail Error: {e}")
        await status.edit_text(f"❌ حدث خطأ: {e}")
