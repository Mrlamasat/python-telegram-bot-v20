import logging
import psycopg2
import asyncio
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 1. الإعدادات
# ==============================
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
SESSION_STRING = "BAIcPawAqsz8F_p2JJmXjf2wJeeg2frJbPyA1FfK3gb4urW94P9VCR5N5apDGsEmeJxtehLGkZs7of6guY6fUqlhG3AnvjVKlxCAHA_xja75TxKgIRqUi-GcjFb_JSguFGioFPTIeX5donwup7_TXxfxCqNURpL_4EPenFnqc6EEbOhRa5Wz7rqE7kv-0KznphGohGYovuftOxoZhUAv0ASyD_pYjcyFBn6798_tmUa-LZyluuxY_msjiigO35H0V8gukbedFVezTLBsuoY6iK61mwXHFeFEkczFfOlEXNp-_ZmU4uBSuFqRdaZOLaRAeaXKoX2eWruWCmCY9bq-VErWbe6GTQAAAAHMKGDXAA"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
ADMIN_CHANNEL = -1003547072209
PUBLIC_CHANNELS = ["@Ramadan4kTV"]

# ==============================
# 2. إعداد العميل
# ==============================
app = Client(
    name="my_session",
    session_string=SESSION_STRING,
    api_id=35405228,
    api_hash="dacba460d875d963bbd4462c5eb554d6",
    workers=20,
    in_memory=True
)

# ==============================
# 3. دالات المساعدة
# ==============================
def hide_text(text):
    return "‌".join(list(text)) if text else "‌"

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
# 4. سحب الحلقات القديمة
# ==============================
async def import_old_videos():
    print("🔄 بدء سحب الفيديوهات القديمة من القناة...")
    try:
        async for msg in app.get_chat_history(ADMIN_CHANNEL, limit=5000):
            if msg.video or msg.document:
                v_id = str(msg.id)
                duration = msg.video.duration if msg.video else getattr(msg.document, "duration", 0)
                db_query(
                    "INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') "
                    "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
                    (ADMIN_CHANNEL, v_id, f"{duration//60}:{duration%60:02d}"), commit=True
                )
        print("✅ انتهى سحب الفيديوهات القديمة، الآن أرسل البوسترات لتسمية المسلسلات.")
    except Exception as e:
        print(f"⚠️ خطأ أثناء السحب: {e}")

# ==============================
# 5. رفع الحلقات الجديدة (أدمن فقط)
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
    await message.reply_text(f"✅ تم الربط بمسلسل: **{message.caption}**\n🔢 أرسل رقم الحلقة فقط:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start"]))
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

    h_title = hide_text(data['title'])
    cap = f"**{center_style('🎬 ' + h_title)}**\n**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**"

    for ch in PUBLIC_CHANNELS:
        try:
            await client.send_photo(ch, photo=data['poster_id'], caption=cap, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مـشـاهـدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر بنجاح.")

# ==============================
# 6. زر start للأعضاء
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("🎬 أهلاً بك في بوت المشاهدة. استخدم روابط الحلقات لمشاهدة المسلسلات.")
    param = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (str(param),), fetchone=True)
    if data:
        related = db_query("SELECT v_id, ep_num FROM episodes WHERE series_id=%s ORDER BY ep_num ASC", (data['series_id'],), fetchall=True)
        bot_info = await client.get_me()
        buttons, row = [], []
        if related:
            for ep in related:
                label = f"🔹 {ep['ep_num']}" if str(ep['v_id']) == str(param) else f"{ep['ep_num']}"
                row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={ep['v_id']}"))
                if len(row) == 5: buttons.append(row); row = []
            if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("🍿 القناة الرئيسية", url="https://t.me/MoAlmohsen")])
        try:
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=ADMIN_CHANNEL,
                message_id=int(data['v_id']),
                caption=f"**{center_style(hide_text(data['title']))}**\n**الحلقة: {data['ep_num']}**",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except:
            await message.reply_text("❌ حدث خطأ، تأكد من وجود البوت كمسؤول في قناة الأرشيف.")
    else:
        await message.reply_text("❌ الحلقة غير موجود.")

# ==============================
# 7. تشغيل البوت بشكل صحيح
# ==============================
async def main():
    await app.start()
    print("🚀 البوت بدأ العمل الآن...")
    await import_old_videos()
    print("🤖 البوت الآن في وضع الاستعداد (Idle)...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
