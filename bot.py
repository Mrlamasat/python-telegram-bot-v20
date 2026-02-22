import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -----------------------------
# 🔐 الإعدادات من GitHub Secrets
# -----------------------------
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")
ADMIN_CHANNEL  = int(os.environ.get("ADMIN_CHANNEL", 0)) # القناة التي ترفع إليها
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")

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
# 1️⃣ إعادة تفعيل نظام الرفع اليدوي (خطوات الرفع)
# -----------------------------
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def start_upload(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO temp_upload (chat_id, v_id, step) VALUES (%s, %s, 'awaiting_poster') "
             "ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'",
             (message.chat.id, v_id), commit=True)
    await message.reply_text("✅ استلمت الفيديو بنجاح.\n📸 الآن أرسل **البوستر** واكتب اسم المسلسل في الوصف (Caption).")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def get_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return
    
    title = message.caption or "مسلسل غير مسمى"
    f_id = message.photo.file_id if message.photo else message.document.file_id
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s",
             (f_id, title, message.chat.id), commit=True)
    await message.reply_text(f"✅ تم حفظ البوستر لـ **{title}**.\n🔢 أرسل الآن **رقم الحلقة** كرسالة نصية:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def get_ep_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_ep': return
    if not message.text.isdigit(): return await message.reply_text("⚠️ يرجى إرسال رقم فقط.")

    db_query("UPDATE temp_upload SET ep_num=%s, step='done' WHERE chat_id=%s",
             (int(message.text), message.chat.id), commit=True)
    
    # نشر الحلقة في القنوات العامة
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    bot = await client.get_me()
    link = f"https://t.me/{bot.username}?start={data['v_id']}"
    
    for ch in PUBLIC_CHANNELS:
        try:
            caption = f"🎬 **{data['title']}**\n🔢 حلقة رقم: {data['ep_num']}"
            await client.send_photo(ch.strip(), photo=data['poster_id'], caption=caption,
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))
        except: pass
    
    # حفظ في قاعدة البيانات النهائية
    db_query("INSERT INTO episodes (v_id, title, ep_num) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO NOTHING",
             (data['v_id'], data['title'], data['ep_num']), commit=True)
    await message.reply_text("🚀 تم النشر في القنوات وتحديث قاعدة البيانات!")

# -----------------------------
# 2️⃣ نظام المشاهدة (البحث في القناة أولاً ثم التحديث)
# -----------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # محاولة جلب الفيديو من القناة الإدارية مباشرة (البحث أولاً)
        try:
            sent_msg = await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=ADMIN_CHANNEL,
                message_id=int(v_id)
            )
            
            # تحديث قاعدة البيانات إذا كانت فارغة أو ناقصة
            title = sent_msg.caption or f"حلقة {v_id}"
            db_query("INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title",
                     (v_id, title), commit=True)
            return

        except Exception as e:
            return await message.reply_text("❌ لم يتم العثور على هذه الحلقة في القناة الإدارية.")

    await message.reply_text("🎬 أهلاً بك يا محمد.\nارفع الحلقات في القناة الإدارية لتبدأ!")

if __name__ == "__main__":
    app.run()
