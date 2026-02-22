import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================
# إعدادات من Environment
# ==========================

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]

ADMIN_CHANNEL = os.environ["ADMIN_CHANNEL"]  # مثال: @MoAlmohsen
PUBLISH_CHANNEL_1 = os.environ["PUBLISH_CHANNEL_1"]  # مثال: @MoAlmohsen
PUBLISH_CHANNEL_2 = os.environ["PUBLISH_CHANNEL_2"]  # مثال: @RamadanSeries26
BOT_USERNAME = os.environ["BOT_USERNAME"]  # مثال: Ramadan4kTVbot

# ==========================

app = Client(
    "ramadan_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==========================
# قاعدة البيانات
# ==========================

def db_query(query, params=(), fetch=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchall() if fetch else None
        if commit:
            conn.commit()
        cur.close()
        return result
    except Exception as e:
        print("DB Error:", e)
        return None
    finally:
        if conn:
            conn.close()

# ==========================
# عند نشر فيديو في القناة الأساسية
# ==========================

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def new_video_handler(client, message):
    v_id = message.id
    title = message.caption or f"Episode {v_id}"

    # حفظ في قاعدة البيانات
    db_query(
        "INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title",
        (str(v_id), title),
        commit=True
    )

    # زر المشاهدة
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "▶ مشاهدة الحلقة",
                url=f"https://t.me/{BOT_USERNAME}?start={v_id}"
            )
        ]
    ])

    # نشر في القناتين
    try:
        await client.copy_message(
            chat_id=PUBLISH_CHANNEL_1,
            from_chat_id=ADMIN_CHANNEL,
            message_id=v_id,
            reply_markup=keyboard
        )

        await client.copy_message(
            chat_id=PUBLISH_CHANNEL_2,
            from_chat_id=ADMIN_CHANNEL,
            message_id=v_id,
            reply_markup=keyboard
        )

        print("✅ تم النشر في القناتين")
    except Exception as e:
        print("❌ خطأ في النشر:", e)

# ==========================
# استقبال start
# ==========================

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):

    if len(message.command) < 2:
        await message.reply_text(
            "🎬 أهلاً بك.\nتفضل بزيارة قناتنا: @MoAlmohsen"
        )
        return

    v_id = message.command[1]

    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=ADMIN_CHANNEL,
            message_id=int(v_id)
        )
    except:
        await message.reply_text("❌ الحلقة غير متوفرة.")

# ==========================

print("🚀 البوت يعمل الآن بنجاح...")
app.run()
