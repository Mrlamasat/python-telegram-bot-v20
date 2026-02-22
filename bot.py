import logging
import psycopg2
import asyncio
import os
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==============================
# 1. الإعدادات
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# ⚠️ الآن نستخدم User Session String بدل BOT TOKEN
USER_SESSION = os.environ.get("USER_SESSION")

# القناة الرئيسية والقنوات العامة للنشر
ADMIN_CHANNEL = "@Ramadan4kTV"
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# تشغيل العميل
app = Client(
    session_name=USER_SESSION,
    api_id=API_ID,
    api_hash=API_HASH,
    workers=20
)

# ==============================
# 2. دوال مساعدة
# ==============================
def hide_text(text):
    if not text: return "‌"
    return "‌".join(list(text))

def center_style(text):
    spacer = "ㅤ" * 8
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
# 3. أوامر الإدارة والرفع
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query(
        "INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') "
        "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
        (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"),
        commit=True
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
        (f_id, message.caption, message.chat.id),
        commit=True
    )
    await message.reply_text(f"✅ تم الربط بمسلسل: **{message.caption}**\n🔢 أرسل رقم الحلقة فقط:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start", "fix"]))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep": return
    if not message.text.isdigit(): return
    
    db_query(
        "UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s",
        (int(message.text), message.chat.id),
        commit=True
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p", callback_data="q_1080p"),
                                InlineKeyboardButton("720p", callback_data="q_720p")]])
    await message.reply_text(f"🎬 حلقة {message.text} جاهزة.. اختر الجودة للنشر:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    db_query(
        "INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) "
        "VALUES (%s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality",
        (data['v_id'], data['poster_id'], data['title'], data['ep_num'], data['duration'], quality),
        commit=True
    )
    
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['v_id']}".replace(" ", "")
    
    h_title = hide_text(data['title'])
    hidden_cap = f"**{center_style('🎬 ' + h_title)}**\n**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**\n**{center_style('⚙️ الجودة: ' + quality)}**"
    
    for ch in PUBLIC_CHANNELS:
        try:
            await client.send_photo(ch, photo=data['poster_id'], caption=hidden_cap,
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر في القنوات.")

# ==============================
# 4. نظام المشاهدة للعضو
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("🎬 أهلاً بك.\nتفضل بزيارة قناتنا: @MoAlmohsen")

    param = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (str(param),), fetchone=True)
    
    if data:
        clean_name = data['title'].replace('‌','').strip()
        related = db_query(
            "SELECT v_id, ep_num FROM episodes WHERE title LIKE %s ORDER BY ep_num ASC",
            (f"%{clean_name}%",),
            fetchall=True
        )
        bot_info = await client.get_me()
        buttons, row = [], []
        if related:
            for ep in related:
                label = f"🔹 {ep['ep_num']}" if str(ep['v_id']) == str(param) else f"{ep['ep_num']}"
                ep_link = f"https://t.me/{bot_info.username}?start={ep['v_id']}".replace(" ", "")
                row.append(InlineKeyboardButton(label, url=ep_link))
                if len(row) == 5: buttons.append(row); row = []
            if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("🍿 شاهد المزيد من الحلقات", url="https://t.me/MoAlmohsen")])
        h_title = hide_text(clean_name)
        final_cap = f"**{center_style('🎬 ' + h_title)}**\n**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**"
        
        try:
            await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(data['v_id']), caption=final_cap, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            print(f"Error: {e}")
            await message.reply_text("⚠️ تأكد من إضافة الحساب كمشرف في القناة.")
    else:
        await message.reply_text("❌ الحلقة غير موجودة.")

# ==============================
# 5. استيراد الحلقات القديمة
# ==============================
@app.on_message(filters.command("import_updated") & filters.private)
async def import_updated_series(client, message):
    await message.reply_text("🔄 بدء الاستيراد من القناة...")

    try:
        chat = await client.get_chat(ADMIN_CHANNEL)
        await message.reply_text(f"✅ الوصول للقناة تم: {chat.title} ({chat.id})")
    except Exception as e:
        await message.reply_text(f"❌ خطأ الوصول للقناة: {e}")
        return

    count = 0
    async for msg in client.get_chat_history(ADMIN_CHANNEL):
        if not (msg.video or (msg.document and msg.document.mime_type.startswith("video"))):
            continue
        caption = (msg.caption or "").strip()
        if not caption:
            continue

        title = caption.lower()
        ep_num = None
        quality = "غير محدد"

        for line in caption.split("\n"):
            if "حلقة" in line:
                ep_num = ''.join(filter(str.isdigit, line))
            elif "الجودة" in line:
                quality = line.split(":")[-1].strip()
        if not ep_num:
            ep_num = "1"

        existing = db_query("SELECT id FROM series WHERE title=%s", (title,), fetchone=True)
        if existing:
            series_id = existing['id']
        else:
            db_query("INSERT INTO series (title, poster_id) VALUES (%s, %s)", (title, msg.photo.file_id if msg.photo else None), commit=True)
            series_id = db_query("SELECT id FROM series WHERE title=%s", (title,), fetchone=True)['id']

        db_query("""
            INSERT INTO episodes (v_id, series_id, ep_num, duration, quality)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (v_id) DO UPDATE
            SET series_id=EXCLUDED.series_id,
                ep_num=EXCLUDED.ep_num,
                quality=EXCLUDED.quality
        """,
        (
            str(msg.id),
            series_id,
            int(ep_num),
            str(msg.video.duration//60) + ":" + f"{msg.video.duration%60:02d}" if msg.video else "0:00",
            quality
        ),
        commit=True)
        count += 1

    await message.reply_text(f"✅ تم تحديث وربط {count} حلقة باسم المسلسل الجديد")

# ==============================
# تشغيل البوت
# ==============================
if __name__ == "__main__":
    app.run()
