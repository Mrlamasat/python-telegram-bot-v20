import logging import psycopg2 import asyncio import os import re from psycopg2.extras import RealDictCursor from pyrogram import Client, filters from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton from pyrogram.errors import FloodWait

==============================

1. الإعدادات

==============================

API_ID = 35405228 API_HASH = "dacba460d875d963bbd4462c5eb554d6" BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0" DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway" ADMIN_CHANNEL = -1003547072209 PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

==============================

2. إعداد العميل

==============================

SESSION_STRING = os.environ.get("USER_SESSION") if not SESSION_STRING: raise ValueError("❌ USER_SESSION فارغ! ضعها في Variables")

app = Client( name="my_bot_session", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, workers=20, in_memory=True )

--- دالات مساعدة ---

def hide_text(text): if not text: return "‌" return "‌".join(list(text))

def center_style(text): spacer = "ㅤ" * 5 return f"{spacer}{text}{spacer}"

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False): conn = None try: conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require") cur = conn.cursor() cur.execute(query, params) result = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None) if commit: conn.commit() cur.close() return result except Exception as e: print(f"DB Error: {e}") return None finally: if conn: conn.close()

==============================

3. استيراد الفيديوهات والصور القديمة تلقائيًا

==============================

@app.on_message(filters.command("import_updated") & filters.private) async def import_updated_series(client, message): status = await message.reply_text("🔄 جاري الاتصال بالقناة وبدء السحب التدريجي...") count = 0 temp_videos = {}  # تخزين الفيديوهات مؤقتًا حسب رقم الحلقة

try:
    target_chat = await client.get_chat(ADMIN_CHANNEL)

    async for msg in client.get_chat_history(target_chat.id):
        # إذا كانت الرسالة فيديو
        if msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type):
            caption = (msg.caption or "").strip()
            nums = re.findall(r'\d+', caption)
            ep_num = int(nums[0]) if nums else None
            if ep_num:
                temp_videos[ep_num] = {
                    'v_id': str(msg.id),
                    'duration': msg.video.duration if msg.video else getattr(msg.document, 'duration', 0),
                    'caption': caption
                }
            continue

        # إذا كانت الرسالة صورة
        if msg.photo or (msg.document and msg.document.mime_type and 'image' in msg.document.mime_type):
            caption = (msg.caption or "").strip()
            nums = re.findall(r'\d+', caption)
            ep_num = int(nums[0]) if nums else None
            if ep_num and ep_num in temp_videos:
                video = temp_videos[ep_num]
                clean_title = caption.split('\n')[0].replace('🎬', '').strip() or video['caption'].split('\n')[0].replace('🎬', '').strip()
                quality = "1080p" if '1080' in caption else ("720p" if '720' in caption else '1080p')

                existing_series = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                if existing_series:
                    series_id = existing_series['id']
                else:
                    db_query("INSERT INTO series (title) VALUES (%s)", (clean_title,), commit=True)
                    res = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                    series_id = res['id'] if res else None

                if series_id:
                    db_query("""
                        INSERT INTO episodes (v_id, series_id, poster_id, title, ep_num, duration, quality)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num
                    """,
                    (
                        video['v_id'], series_id, msg.photo.file_id if msg.photo else msg.document.file_id,
                        clean_title, ep_num, f"{video['duration']//60}:{video['duration']%60:02d}", quality
                    ), commit=True)
                    count += 1
                    if count % 5 == 0:
                        await status.edit_text(f"🔄 جاري العمل.. تم ربط {count} حلقة حتى الآن.")
                    await asyncio.sleep(1.5)  # توقف لتجنب Flood Wait

    await status.edit_text(f"✅ تم بنجاح! ربط {count} حلقة بالمسلسلات.")

except Exception as e:
    await status.edit_text(f"❌ حدث خطأ أثناء السحب: {e}")

==============================

4. باقي أوامر البوت (رفع الفيديو والصورة والعضو)

كما في الكود السابق

==============================

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document)) async def on_video(client, message): v_id = str(message.id) sec = message.video.duration if message.video else getattr(message.document, "duration", 0) db_query( "INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') " "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"), commit=True ) await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن واكتب اسم المسلسل في الوصف.")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document)) async def on_poster(client, message): state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True) if not state or state['step'] != 'awaiting_poster': return if not message.caption: return await message.reply_text("⚠️ اكتب اسم المسلسل في وصف الصورة.") f_id = message.photo.file_id if message.photo else message.document.file_id db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", (f_id, message.caption, message.chat.id), commit=True) await message.reply_text(f"✅ تم الربط بمسلسل: {message.caption}\n🔢 أرسل رقم الحلقة فقط:")

==============================

تشغيل البوت

==============================

if name == "main": print("🚀 البوت بدأ العمل الآن...") app.run()
