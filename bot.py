import logging
import psycopg2
import asyncio
import os
import re
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 1. الإعدادات
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
ADMIN_CHANNEL = -1003547072209
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# ==============================
# 2. إعداد العميل
# ==============================
SESSION_STRING = os.environ.get("USER_SESSION")
if not SESSION_STRING:
    raise ValueError("❌ USER_SESSION فارغ!")

app = Client(
    name="my_session_manager",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    workers=20,
    in_memory=True
)

# --- دالات المساعدة ---
def hide_text(text):
    if not text: return "‌"
    return "‌".join(list(text))

def center_style(text):
    spacer = "ㅤ" * 5
    return f"{spacer}{text}{spacer}"

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None)
        if commit: conn.commit()
        cur.close()
        return result
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# ==============================
# 3. استيراد الفيديوهات القديمة
# ==============================
@app.on_message(filters.command("import_updated") & filters.private)
async def import_updated_series(client, message):
    status = await message.reply_text("🔄 جاري استيراد الفيديوهات القديمة...")
    count = 0
    try:
        target_chat = await client.get_chat(ADMIN_CHANNEL)

        async for msg in client.get_chat_history(target_chat.id):
            if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                continue

            # اجلب caption إذا موجود
            caption = (msg.caption or "").strip()

            # إذا caption موجود نحاول استخراج الاسم ورقم الحلقة والجودة
            if caption:
                clean_title = caption.split('\n')[0].replace('🎬', '').strip()
                nums = re.findall(r'\d+', caption)
                ep_num = int(nums[0]) if nums else 1
                quality = "1080p" if "1080" in caption else "720p" if "720" in caption else "غير محدد"
            else:
                clean_title = f"مسلسل غير معروف"  # اسم افتراضي
                ep_num = 1
                quality = "غير محدد"

            # ابحث عن بوستر موجود لنفس المسلسل في قاعدة البيانات
            poster = db_query("SELECT poster_id FROM series WHERE title=%s", (clean_title,), fetchone=True)
            poster_id = poster['poster_id'] if poster else None

            # 1. إنشاء أو تحديث المسلسل
            existing_series = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
            if existing_series:
                series_id = existing_series['id']
            else:
                db_query("INSERT INTO series (title, poster_id) VALUES (%s, %s)", (clean_title, poster_id), commit=True)
                res = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                series_id = res['id'] if res else None

            # 2. إدخال الحلقة
            if series_id:
                db_query("""
                    INSERT INTO episodes (v_id, series_id, title, ep_num, duration, quality, poster_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (v_id) DO UPDATE 
                    SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num, poster_id=EXCLUDED.poster_id
                """, (str(msg.id), series_id, clean_title, ep_num, "0:00", quality, poster_id), commit=True)
                count += 1
                if count % 10 == 0:
                    await status.edit_text(f"🔄 جاري العمل.. تم ربط {count} حلقة.")

        await status.edit_text(f"✅ تم بنجاح! ربط {count} حلقة بالمسلسلات.")
    except Exception as e:
        await status.edit_text(f"❌ حدث خطأ أثناء الاستيراد: {e}")

# ==============================
# 4. أوامر الرفع اليدوي والبوت
# (لم تتغير من نسختك السابقة)
# ==============================

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query(
        "INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') "
        "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
        (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"), commit=True
    )
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن واكتب اسم المسلسل في الوصف.")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return
    if not message.caption:
        return await message.reply_text("⚠️ اكتب اسم المسلسل في وصف الصورة.")

    f_id = message.photo.file_id if message.photo else message.document.file_id
    db_query(
        "UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s",
        (f_id, message.caption, message.chat.id), commit=True
    )
    await message.reply_text(f"✅ تم الربط بمسلسل: {message.caption}\n🔢 أرسل رقم الحلقة فقط:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start", "import_updated"]))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep": return
    if not message.text.isdigit(): return

    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s", (int(message.text), message.chat.id), commit=True)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p", callback_data="q_1080p"), InlineKeyboardButton("720p", callback_data="q_720p")]])
    await message.reply_text(f"🎬 حلقة {message.text} جاهزة.. اختر الجودة:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return

    db_query("INSERT INTO series (title, poster_id) VALUES (%s, %s) ON CONFLICT (title) DO NOTHING", (data['title'], data['poster_id']), commit=True)
    s_data = db_query("SELECT id FROM series WHERE title=%s", (data['title'],), fetchone=True)

    db_query(
        "INSERT INTO episodes (v_id, series_id, poster_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num",
        (data['v_id'], s_data['id'], data['poster_id'], data['title'], data['ep_num'], data['duration'], quality), commit=True
    )

    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['v_id']}"
    cap = f"**{center_style(hide_text(data['title']))}**\n**الحلقة: {data['ep_num']}**"

    for ch in PUBLIC_CHANNELS:
        try: await client.send_photo(ch, photo=data['poster_id'], caption=cap, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر بنجاح.")

# ==============================
# 5. تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت بدأ العمل الآن...")
    app.run()
