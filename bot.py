import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -----------------------------
# 🔐 الإعدادات المحدثة حسب قنواتك
# -----------------------------
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")

# القنوات التي حددتها
ADMIN_CHANNEL   = "@Ramadan4kTV"    # قناة رفع الحلقات
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"] # قنوات النشر

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
# 1️⃣ إصلاح نظام الرفع اليدوي (خطوات الرفع)
# -----------------------------
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def start_upload(client, message):
    v_id = str(message.id)
    # تصفير أي عملية سابقة وبدء عملية جديدة
    db_query("INSERT INTO temp_upload (chat_id, v_id, step) VALUES (%s, %s, 'awaiting_poster') "
             "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
             (message.chat.id, v_id), commit=True)
    await message.reply_text("✅ تم استلام الحلقة في قناة الرفع.\n📸 أرسل الآن **البوستر** واكتب اسم المسلسل في الوصف (Caption).")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def get_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return
    
    title = message.caption or "مسلسل غير مسمى"
    f_id = message.photo.file_id if message.photo else message.document.file_id
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s",
             (f_id, title, message.chat.id), commit=True)
    await message.reply_text(f"✅ تم ربط البوستر بمسلسل: **{title}**.\n🔢 أرسل الآن **رقم الحلقة** كرسالة نصية:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def get_ep_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_ep': return
    if not message.text.isdigit(): return await message.reply_text("⚠️ أرسل رقم الحلقة فقط (أرقام).")

    ep_num = int(message.text)
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    
    # تجهيز رابط المشاهدة
    bot_me = await client.get_me()
    link = f"https://t.me/{bot_me.username}?start={data['v_id']}"
    
    # النشر في القنوات العامة التي حددتها
    for ch in PUBLIC_CHANNELS:
        try:
            caption = f"🎬 **{data['title']}**\n🔢 حلقة رقم: {ep_num}"
            await client.send_photo(ch, photo=data['poster_id'], caption=caption,
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=link)]]))
        except Exception as e:
            print(f"Error publishing to {ch}: {e}")
    
    # حفظ البيانات النهائية وحذف المؤقتة
    db_query("INSERT INTO episodes (v_id, title, ep_num) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO NOTHING",
             (data['v_id'], data['title'], ep_num), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (message.chat.id,), commit=True)
    
    await message.reply_text("🚀 تم النشر بنجاح في القنوات وتحديث قاعدة البيانات.")

# -----------------------------
# 2️⃣ نظام المشاهدة (البحث في المصدر ثم التحديث)
# -----------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # محاولة جلب الفيديو من قناة الرفع مباشرة
        try:
            sent_msg = await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=ADMIN_CHANNEL,
                message_id=int(v_id)
            )
            
            # تحديث القاعدة تلقائياً إذا كانت فارغة
            title = sent_msg.caption or f"حلقة {v_id}"
            db_query("INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO NOTHING",
                     (v_id, title), commit=True)
            return

        except Exception as e:
            print(f"Copy Error: {e}")
            return await message.reply_text("❌ لم يتم العثور على الحلقة في قناة المصدر.")

    await message.reply_text("🎬 أهلاً بك يا محمد.\nارفع حلقة جديدة في قناة @Ramadan4kTV للبدء.")

if __name__ == "__main__":
    app.run()
