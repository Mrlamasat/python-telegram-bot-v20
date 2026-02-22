import os
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -----------------------------
# 🔐 الإعدادات
# -----------------------------
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")

ADMIN_CHANNEL   = "@Ramadan4kTV"
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

app = Client("mo_userbot", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)

def db_query(query, params=(), fetchone=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchone() if fetchone else None
        if commit: conn.commit()
        cur.close()
        return res
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# -----------------------------
# 1️⃣ نظام الرفع اليدوي (إصلاح التعطل)
# -----------------------------
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def handle_new_video(client, message):
    v_id = str(message.id)
    # تفعيل نظام الخطوات في قاعدة البيانات
    db_query("INSERT INTO temp_upload (chat_id, v_id, step) VALUES (%s, %s, 'awaiting_poster') "
             "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
             (message.chat.id, v_id), commit=True)
    await message.reply_text("📥 استلمت الحلقة.\n📸 أرسل **البوستر** الآن واكتب اسم المسلسل في الوصف.")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def handle_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if state and state['step'] == 'awaiting_poster':
        title = message.caption or "مسلسل جديد"
        f_id = message.photo.file_id if message.photo else message.document.file_id
        db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s",
                 (f_id, title, message.chat.id), commit=True)
        await message.reply_text(f"✅ تم حفظ البوستر لـ **{title}**.\n🔢 أرسل الآن **رقم الحلقة**:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def handle_ep_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if state and state['step'] == 'awaiting_ep' and message.text.isdigit():
        data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
        bot = await client.get_me()
        link = f"https://t.me/{bot.username}?start={data['v_id']}"
        
        # النشر التلقائي
        for ch in PUBLIC_CHANNELS:
            try:
                await client.send_photo(ch, photo=data['poster_id'], 
                                        caption=f"🎬 **{data['title']}**\n🔢 حلقة رقم: {message.text}",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
            except: pass
        
        db_query("INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT DO NOTHING", (data['v_id'], data['title']), commit=True)
        db_query("DELETE FROM temp_upload WHERE chat_id=%s", (message.chat.id,), commit=True)
        await message.reply_text("🚀 تم النشر بنجاح!")

# -----------------------------
# 2️⃣ نظام المشاهدة (لروابط القديمة والجديدة)
# -----------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            # محاولة جلب الفيديو مباشرة من القناة الإدارية باستخدام ID الرابط
            sent = await client.copy_message(chat_id=message.chat.id, from_chat_id=ADMIN_CHANNEL, message_id=int(v_id))
            # تحديث القاعدة تلقائياً للحلقات القديمة
            db_query("INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT DO NOTHING", (v_id, sent.caption or "حلقة قديمة"), commit=True)
            return
        except Exception:
            return await message.reply_text("❌ عذراً، هذه الحلقة (الرابط القديم) لم تعد موجودة في قناة المصدر.")

    await message.reply_text(f"🎬 أهلاً بك يا محمد.\nارفع حلقة جديدة في {ADMIN_CHANNEL} أو ابحث عن مسلسلك.")

if __name__ == "__main__":
    app.run()
