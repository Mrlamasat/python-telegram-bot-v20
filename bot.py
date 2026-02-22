import logging
import psycopg2
import asyncio
import os
import re
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==============================
# 1. الإعدادات
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
ADMIN_CHANNEL_USERNAME = "Ramadan4kTV"
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

SESSION_STRING = os.environ.get("USER_SESSION")
if not SESSION_STRING:
    raise ValueError("❌ USER_SESSION فارغ!")

app = Client(
    "my_session",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    workers=20,
    in_memory=True
)

# ==============================
# 2. دوال مساعدة
# ==============================
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
# 3. استيراد الحلقات القديمة
# ==============================
@app.on_message(filters.command("import_old") & filters.private)
async def import_old(client, message):
    status = await message.reply_text("🔄 جاري الاتصال بالقناة وبدء السحب...")
    count = 0
    try:
        target_chat = await client.get_chat(ADMIN_CHANNEL_USERNAME)
        async for msg in client.get_chat_history(target_chat.id):
            if not (msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)):
                continue
            caption = (msg.caption or "").strip()
            if not caption: continue
            clean_title = caption.split('\n')[0].replace('🎬','').strip()
            nums = re.findall(r'\d+', caption)
            ep_num = int(nums[0]) if nums else 1
            quality = "1080p" if "1080" in caption else "720p"

            existing_series = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
            if existing_series:
                series_id = existing_series['id']
            else:
                db_query("INSERT INTO series (title) VALUES (%s)", (clean_title,), commit=True)
                res = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                series_id = res['id'] if res else None

            if series_id:
                db_query("""
                    INSERT INTO episodes (v_id, series_id, title, ep_num, duration, quality)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num
                """, (str(msg.id), series_id, clean_title, ep_num, "0:00", quality), commit=True)
                count += 1
                if count % 10 == 0:
                    await status.edit_text(f"🔄 جاري العمل.. تم سحب {count} حلقة حتى الآن.")
        await status.edit_text(f"✅ تم بنجاح! سحب {count} حلقة وربطها بالمسلسلات.")
    except Exception as e:
        await status.edit_text(f"❌ حدث خطأ أثناء السحب: {e}")

# ==============================
# 4. رفع فيديو جديد
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL_USERNAME) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query(
        "INSERT INTO temp_upload (chat_id,v_id,duration,step) VALUES (%s,%s,%s,'awaiting_poster') "
        "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
        (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"), commit=True
    )
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن واكتب اسم المسلسل في الوصف.")

# ==============================
# 5. رفع البوستر وربط الاسم
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL_USERNAME) & (filters.photo | filters.document))
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s",(message.chat.id,), fetchone=True)
    if not state or state['step']!='awaiting_poster': return
    if not message.caption:
        return await message.reply_text("⚠️ اكتب اسم المسلسل في وصف الصورة.")
    f_id = message.photo.file_id if message.photo else message.document.file_id
    db_query(
        "UPDATE temp_upload SET poster_id=%s,title=%s,step='awaiting_ep' WHERE chat_id=%s",
        (f_id,message.caption,message.chat.id), commit=True
    )
    await message.reply_text(f"✅ تم ربط المسلسل: **{message.caption}**\n🔢 أرسل رقم الحلقة:")

# ==============================
# 6. تحديد رقم الحلقة وجودتها
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL_USERNAME) & filters.text & ~filters.command(["start","import_old"]))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s",(message.chat.id,), fetchone=True)
    if not state or state['step']!="awaiting_ep": return
    if not message.text.isdigit(): return
    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s",(int(message.text),message.chat.id), commit=True)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p",callback_data="q_1080p"),
                                InlineKeyboardButton("720p",callback_data="q_720p")]])
    await message.reply_text(f"🎬 حلقة {message.text} جاهزة.. اختر الجودة:", reply_markup=kb)

# ==============================
# 7. نشر الفيديو بعد اختيار الجودة
# ==============================
@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s",(query.message.chat.id,), fetchone=True)
    if not data: return
    db_query("INSERT INTO series (title,poster_id) VALUES (%s,%s) ON CONFLICT(title) DO NOTHING",
             (data['title'],data['poster_id']), commit=True)
    s_data = db_query("SELECT id FROM series WHERE title=%s",(data['title'],), fetchone=True)
    db_query("INSERT INTO episodes (v_id,series_id,poster_id,title,ep_num,duration,quality) VALUES (%s,%s,%s,%s,%s,%s,%s) "
             "ON CONFLICT(v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num",
             (data['v_id'],s_data['id'],data['poster_id'],data['title'],data['ep_num'],data['duration'],quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s",(query.message.chat.id,), commit=True)
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['v_id']}"
    cap = f"**{center_style(hide_text(data['title']))}**\n**الحلقة: {data['ep_num']}**"
    for ch in PUBLIC_CHANNELS:
        try:
            await client.send_photo(ch,photo=data['poster_id'],caption=cap,
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر بنجاح.")

# ==============================
# 8. نظام المشاهدة للعضو
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command)<2:
        return await message.reply_text("🎬 أهلاً بك.\nتفضل بزيارة قناتنا: @MoAlmohsen")
    param = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s",(str(param),), fetchone=True)
    if data:
        related = db_query("SELECT v_id,ep_num FROM episodes WHERE series_id=%s ORDER BY ep_num ASC",(data['series_id'],), fetchall=True)
        bot_info = await client.get_me()
        buttons,row=[],[]
        if related:
            for ep in related:
                label = f"🔹 {ep['ep_num']}" if str(ep['v_id'])==str(param) else f"{ep['ep_num']}"
                row.append(InlineKeyboardButton(label,url=f"https://t.me/{bot_info.username}?start={ep['v_id']}"))
                if len(row)==5: buttons.append(row); row=[]
            if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("🍿 القناة الرئيسية",url="https://t.me/MoAlmohsen")])
        try:
            await client.copy_message(message.chat.id,ADMIN_CHANNEL_USERNAME,int(data['v_id']),
                                      caption=f"**{center_style(hide_text(data['title']))}**\n**الحلقة: {data['ep_num']}**",
                                      reply_markup=InlineKeyboardMarkup(buttons))
        except:
            await message.reply_text("❌ خطأ في جلب الفيديو.")
    else:
        await message.reply_text("❌ الحلقة غير موجودة.")

# ==============================
# 9. تشغيل البوت
# ==============================
if __name__=="__main__":
    print("🚀 البوت بدأ العمل الآن...")
    app.run()
