import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

# ==============================
# إعدادات البوت وPostgreSQL
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
DATABASE_URL = os.getenv("DATABASE_URL")  # مثال: postgresql://user:pass@host:port/dbname
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL")  # قناة المصدر للتحميل

app = Client("my_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# ==============================
# قاعدة البيانات
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
# رفع الحلقات (Admin only)
# ==============================
@app.on_message(filters.private & filters.user(int(os.getenv("ADMIN_ID"))) & filters.command("upload"))
async def upload_episode(client, message):
    # خطوات رفع الحلقة
    await message.reply_text("📥 ارسل الرابط أو الوتستر للحلقة:")
    
    # انتظار الرد على الوتستر
    wester_msg = await client.listen(message.chat.id)
    wester = wester_msg.text
    
    await message.reply_text("🔢 ارسل رقم الحلقة:")
    ep_msg = await client.listen(message.chat.id)
    episode_number = int(ep_msg.text)
    
    await message.reply_text("🎞 اختر الجودة (مثال: 720p, 1080p):")
    quality_msg = await client.listen(message.chat.id)
    quality = quality_msg.text

    # تحميل الحلقة من قناة المصدر
    # يفترض أن القناة SOURCE_CHANNEL متاحة
    async for msg in client.search_messages(SOURCE_CHANNEL, limit=100):
        if str(episode_number) in msg.text:
            file_id = msg.video.file_id if msg.video else None
            if file_id:
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
                break

# ==============================
# مشاهدة الحلقة
# ==============================
@app.on_message(filters.private & filters.command("watch"))
async def watch_episode(client, message):
    # جلب آخر حلقة
    conn = await asyncpg.connect(DATABASE_URL)
    episode = await conn.fetchrow("""
        SELECT * FROM episodes
        ORDER BY episode_number DESC
        LIMIT 1;
    """)
    await conn.close()
    
    if episode:
        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("مشاهدة الآن", callback_data=f"watch_{episode['episode_number']}")]]
        )
        await message.reply_video(episode["file_id"], caption=f"الحلقة {episode['episode_number']} - جودة {episode['quality']}", reply_markup=buttons)
    else:
        await message.reply_text("⚠️ لا توجد حلقات متاحة حاليا.")

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
        await callback_query.message.edit_video(episode["file_id"], caption=f"الحلقة {episode_number} - جودة {episode['quality']}")
    else:
        await callback_query.answer("⚠️ الحلقة غير موجودة في الأرشيف.", show_alert=True)

# ==============================
# تشغيل البوت
# ==============================
async def main():
    await init_db()
    await app.start()
    print("🚀 البوت جاهز للعمل!")
    await idle()

if __name__ == "__main__":
    from pyrogram import idle
    asyncio.run(main())
