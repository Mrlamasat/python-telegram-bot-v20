import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 🔐 قراءة المتغيرات من البيئة
# ==============================
SESSION_STRING = os.environ.get("SESSION_STRING")
BOT_TOKEN      = os.environ.get("BOT_TOKEN")
DATABASE_URL   = os.environ.get("DATABASE_URL")
ADMIN_CHANNEL  = int(os.environ.get("ADMIN_CHANNEL"))
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")
SOURCE_CHANNEL = os.environ.get("SOURCE_CHANNEL")
API_ID         = int(os.environ.get("API_ID"))
API_HASH       = os.environ.get("API_HASH")

# تحقق من وجود المتغيرات
if not all([SESSION_STRING, BOT_TOKEN, DATABASE_URL, ADMIN_CHANNEL, PUBLIC_CHANNELS, API_ID, API_HASH, SOURCE_CHANNEL]):
    raise ValueError("❌ أحد متغيرات البيئة مفقود. تحقق من SESSION_STRING, DATABASE_URL, ADMIN_CHANNEL, PUBLIC_CHANNELS, BOT_TOKEN, API_ID, API_HASH, SOURCE_CHANNEL.")

# ==============================
# ⚡ تشغيل البوت
# ==============================
app = Client(
    "mo_userbot",
    session_string=SESSION_STRING,
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
    workers=20,
    sleep_threshold=60
)

# ==============================
# 📦 دوال مساعدة
# ==============================
def hide_text(text):
    return "‌".join(list(text)) if text else "‌"

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
# 🔄 جلب الحلقات القديمة
# ==============================
async def fetch_old_videos():
    """
    جلب الحلقات القديمة من القناة المصدرية وتخزينها في قاعدة البيانات
    """
    print("⏳ جاري جلب الحلقات القديمة...")
    
    try:
        async for message in app.get_history(SOURCE_CHANNEL, limit=200):
            if not message.video:
                continue  # تجاهل الرسائل غير الفيديو
            
            v_id = str(message.id)
            title = message.caption or f"فيديو {v_id}"
            poster_id = message.photo.file_id if message.photo else None

            db_query(
                """
                INSERT INTO episodes (v_id, title, poster_id) 
                VALUES (%s, %s, %s)
                ON CONFLICT (v_id) DO UPDATE 
                SET title=EXCLUDED.title, poster_id=EXCLUDED.poster_id
                """,
                (v_id, title, poster_id),
                commit=True
            )
            print(f"📥 تم جلب حلقة قديمة: {v_id}")
        
        print("✅ تم الانتهاء من جلب الحلقات القديمة.")
    except Exception as e:
        print(f"⚠️ حدث خطأ أثناء جلب الحلقات القديمة: {e}")

# ==============================
# 🔄 جلب الحلقات الجديدة من القناة المصدرية
# ==============================
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def handle_source_video(client, message):
    v_id = str(message.id)
    title = message.caption or f"فيديو {v_id}"
    poster_id = message.photo.file_id if message.photo else None

    db_query(
        "INSERT INTO episodes (v_id, title, poster_id) VALUES (%s, %s, %s) "
        "ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title, poster_id=EXCLUDED.poster_id",
        (v_id, title, poster_id),
        commit=True
    )
    print(f"📥 تم جلب حلقة جديدة: {v_id}")

# ==============================
# 🔄 تحديث العنوان إذا تم تعديل الفيديو
# ==============================
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def handle_source_edit(client, message):
    v_id = str(message.id)
    title = message.caption or f"فيديو {v_id}"
    db_query("UPDATE episodes SET title=%s WHERE v_id=%s", (title, v_id), commit=True)
    print(f"🔄 تم تحديث الحلقة: {v_id}")

# ==============================
# 🔍 البحث وإرسال الحلقة
# ==============================
@app.on_message(filters.private & filters.text & ~filters.me & ~filters.outgoing)
async def search_bot(client, message):
    txt = message.text.strip()
    if len(txt) < 2: 
        return

    search_query = f"%{txt}%"
    results = db_query("SELECT v_id, title FROM episodes WHERE title ILIKE %s LIMIT 5", (search_query,), fetchall=True)
    
    if results:
        for res in results:
            v_id = str(res['v_id'])
            link = f"https://t.me/{SOURCE_CHANNEL.strip('@')}/{v_id}"  # الرابط الأصلي للقناة
            try:
                await app.copy_message(chat_id=message.chat.id, from_chat_id=SOURCE_CHANNEL, message_id=int(v_id))
                await app.send_message(
                    chat_id=message.chat.id,
                    text="▶️ شاهد الحلقة الآن",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶ مشاهدة الحلقة", url=link)]])
                )
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Error sending video {v_id}: {e}")

# ==============================
# ▶️ /start لعرض الحلقة عند الضغط على زر
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"🎬 أهلاً بك.\nتفضل بزيارة قناتنا: {PUBLIC_CHANNELS[0]}")
    
    v_id = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
    if not data:
        return await message.reply_text("❌ الحلقة غير موجودة.")
    
    link = f"https://t.me/{SOURCE_CHANNEL.strip('@')}/{v_id}"  # الرابط الأصلي للقناة
    final_caption = f"**{hide_text(data['title'])}**"

    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=final_caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶ مشاهدة الحلقة", url=link)]])
        )
    except Exception as e:
        print(f"Error sending /start video: {e}")
        await message.reply_text("⚠️ حدث خطأ أثناء جلب الحلقة.")

# ==============================
# ▶️ تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت يعمل الآن على الاستضافة...")
    asyncio.run(fetch_old_videos())  # جلب الحلقات القديمة عند التشغيل
    app.run()
