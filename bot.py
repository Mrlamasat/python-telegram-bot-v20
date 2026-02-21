@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    # التحقق من أن الأدمن في مرحلة إدخال رقم الحلقة
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num": return
    
    if not message.text.isdigit():
        return await message.reply_text("⚠️ يرجى إرسال رقم صحيح (مثلاً: 5)")
    
    # حفظ الرقم والانتقال لاختيار الجودة
    db_query("UPDATE temp_upload SET ep_num=%s, step=%s WHERE chat_id=%s", 
             (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
    
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("720p", callback_data="q_720p"),
        InlineKeyboardButton("1080p", callback_data="q_1080p")
    ]])
    await message.reply_text("✨ اختر الجودة الآن لإتمام النشر:", reply_markup=btns)

@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    
    # جلب البيانات المؤقتة
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), fetchone=True)
    if not data:
        return await query.answer("❌ انتهت الجلسة أو البيانات مفقودة", show_alert=True)
        
    v_id, poster_id, title, ep_num, duration = data

    # 1. الحفظ في القاعدة النهائية (مع تحديث البيانات إذا كانت موجودة لمنع الخطأ)
    db_query('''INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) 
                VALUES (%s, %s, %s, %s, %s, %s) 
                ON CONFLICT (v_id) DO UPDATE SET 
                poster_id=EXCLUDED.poster_id, title=EXCLUDED.title, 
                ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality''', 
             (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    
    # مسح البيانات المؤقتة
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = (f"🎬 **{title}**\n" if title else "") + f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])

    # 2. معالجة البوستر بأمان تام
    await query.message.edit_text("⏳ جاري معالجة الصورة والنشر...")
    
    file_path = None
    try:
        file_path = await client.download_media(poster_id)
        if file_path:
            with Image.open(file_path) as img:
                # التأكد من نمط الصورة لتحويل WebP أو أي صيغة أخرى
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGBA")
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    final_img = bg
                else:
                    final_img = img.convert("RGB")
                
                bio = io.BytesIO()
                bio.name = "poster.png"
                final_img.save(bio, "PNG")
                bio.seek(0)
                await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption, reply_markup=markup)
        else:
            raise Exception("Download failed")
            
    except Exception as e:
        logger.error(f"Poster Fix Error: {e}")
        # في حال فشل كل شيء، أرسل المعرف الأصلي كما هو
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)
    
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

    await query.message.edit_text("🚀 تم النشر بنجاح في القناة!")
