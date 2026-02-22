import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
DATABASE_URL = os.getenv("DATABASE_URL")
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

app = Client("my_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# ==============================
# إعداد قاعدة البيانات
# ==============================
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id SERIAL PRIMARY KEY,
            episode_number INT UNIQUE,
            file_id TEXT,
            quality TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.close()

# ==============================
# رفع الحلقات (Admin فقط)
# ==============================
@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.command("upload"))
async def upload_episode(client, message):
    await message.reply_text("📥 أرسل رابط أو الوستر للحلقة:")
    wester_msg = await client.listen(message.chat.id)
    wester = wester_msg.text

    await message.reply_text("🔢 ارسل رقم الحلقة:")
    ep_msg = await client.listen(message.chat.id)
    episode_number = int(ep_msg.text)

    await message.reply_text("🎞 اختر الجودة (مثال: 720p, 1080p):")
    quality_msg = await client.listen(message.chat.id)
    quality = quality_msg.text

    # البحث في قناة المصدر عن الحلقة
    file_id = None
    async for msg in client.search_messages(SOURCE_CHANNEL, limit=100):
        if str(episode_number) in (msg.text or ""):
            file_id = msg.video.file_id if msg.video else None
            break

    if not file_id:
        await message.reply_text("⚠️ لم يتم العثور على الفيديو في قناة المصدر.")
        return

    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO episodes (episode_number, file_id, quality)
        VALUES ($1, $2, $3)
        ON CONFLICT (episode_number) DO UPDATE
        SET file_id = EXCLUDED.file_id,
            quality = EXCLUDED.quality;
    """, episode_number, file_id, quality)
    await conn.close()

    await message.reply_text(f"✅ تم أرشفة الحلقة {episode_number} بالجودة {quality}")

# ==============================
# مشاهدة الحلقات
# ==============================
@app.on_message(filters.private & filters.command("watch"))
async def watch_episode(client, message):
    conn = await asyncpg.connect(DATABASE_URL)
    episodes = await conn.fetch("""
        SELECT * FROM episodes
        ORDER BY episode_number DESC;
    """)
    await conn.close()

    if not episodes:
        await message.reply_text("⚠️ لا توجد حلقات متاحة حاليا.")
        return

    buttons = [
        [InlineKeyboardButton(f"الحلقة {ep['episode_number']}", callback_data=f"watch_{ep['episode_number']}")]
        for ep in episodes[-5:]  # آخر 5 حلقات
    ]

    await message.reply_text("🎬 اختر الحلقة للمشاهدة:", reply_markup=InlineKeyboardMarkup(buttons))

# ==============================
# التعامل مع أزرار المشاهدة
# ==============================
@app.on_callback_query(filters.regex(r"watch_(\d+)"))
async def callback_watch(client, callback_query):
    episode_number = int(callback_query.data.split("_")[1])
    conn = await asyncpg.connect(DATABASE_URL)
    episode = await conn.fetchrow("SELECT * FROM episodes WHERE episode_number=$1;", episode_number)
    await conn.close()

    if episode:
        await callback_query.message.edit_media(
            media=episode["file_id"],
            reply_markup=None,
            caption=f"الحلقة {episode_number} - جودة {episode['quality']}"
        )
    else:
        await callback_query.answer("⚠️ الحلقة غير موجودة في الأرشيف.", show_alert=True)

# ==============================
# تشغيل البوت
# ==============================
async def main():
    await init_db()
    await app.start()
    print("🚀 البوت جاهز للعمل!")
    await asyncio.Event().wait()  # للحفاظ على تشغيل البوت

if __name__ == "__main__":
    asyncio.run(main())
