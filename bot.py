import os
import asyncio
import asyncpg
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==============================
# 🔐 قراءة المتغيرات من البيئة
# ==============================
SESSION_STRING = os.environ.get("SESSION_STRING")
BOT_TOKEN      = os.environ.get("BOT_TOKEN")
DATABASE_URL   = os.environ.get("DATABASE_URL")
ADMIN_CHANNEL  = int(os.environ.get("ADMIN_CHANNEL", 0))
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")
SOURCE_CHANNEL = os.environ.get("SOURCE_CHANNEL")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")

# تحقق من المتغيرات
if not all([SESSION_STRING, BOT_TOKEN, DATABASE_URL, ADMIN_CHANNEL, API_ID, API_HASH, SOURCE_CHANNEL]) or not PUBLIC_CHANNELS:
    raise ValueError("❌ أحد متغيرات البيئة مفقود أو PUBLIC_CHANNELS فارغة")

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

# ==============================
# 🗄 إعداد قاعدة البيانات
# ==============================
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    await conn.close()

async def db_execute(query, *params, fetch=False, fetchval=False, fetchrow=False):
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    try:
        if fetch:
            return await conn.fetch(query, *params)
        if fetchval:
            return await conn.fetchval(query, *params)
        if fetchrow:
            return await conn.fetchrow(query, *params)
        return await conn.execute(query, *params)
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        await conn.close()

# ==============================
# 🔄 جلب الحلقات من القناة المصدرية
# ==============================
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def handle_source_video(client, message):
    v_id = str(message.id)
    title = message.caption or f"فيديو {v_id}"
    poster_id = message.video.thumbs[0].file_id if message.video.thumbs else None

    await db_execute(
        """
        INSERT INTO episodes (v_id, title, poster_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (v_id)
        DO UPDATE SET title=EXCLUDED.title, poster_id=EXCLUDED.poster_id
        """,
        v_id, title, poster_id
    )
    print(f"📥 تم جلب حلقة جديدة: {v_id}")

# ==============================
# 🔄 تحديث العنوان إذا تم تعديل الفيديو
# ==============================
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def handle_source_edit(client, message):
    v_id = str(message.id)
    title = message.caption or f"فيديو {v_id}"
    await db_execute("UPDATE episodes SET title=$1 WHERE v_id=$2", title, v_id)
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
    results = await db_execute(
        "SELECT v_id, title FROM episodes WHERE title ILIKE $1 ORDER BY created_at DESC LIMIT 5",
        search_query, fetch=True
    )

    if results:
        bot_info = await client.get_me()
        for res in results:
            v_id = str(res['v_id'])
            link = f"https://t.me/{bot_info.username}?start={v_id}"
            try:
                await app.copy_message(chat_id=message.chat.id, from_chat_id=SOURCE_CHANNEL, message_id=int(v_id))
                await app.send_message(
                    chat_id=message.chat.id,
                    text="▶️ شاهد الحلقة الآن",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶ مشاهدة الحلقة", url=link)]])
                )
                await asyncio.sleep(1)
            except FloodWait as e:
                print(f"⏱ Flood wait {e.x}s")
                await asyncio.sleep(e.x)
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
    data = await db_execute("SELECT * FROM episodes WHERE v_id=$1", v_id, fetchrow=True)
    if not data:
        return await message.reply_text("❌ الحلقة غير موجودة.")

    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
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
    asyncio.run(init_db())
    app.run()
