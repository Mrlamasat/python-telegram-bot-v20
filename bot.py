import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ======= المتغيرات من GitHub Secrets =======
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]

ADMIN_CHANNEL = "@Ramadan4kTV"        # مصدر الحلقات
FORWARD_CHANNEL = "@RamadanSeries26"  # قناة النشر
BOT_USERNAME = "Ramadan4kTVbot"

# ======= تشغيل البوت =======
app = Client(
    "ramadan_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ======= قاعدة البيانات =======
def db_query(query, params=(), commit=False):
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute(query, params)
    if commit:
        conn.commit()
    cur.close()
    conn.close()

# ======= أمر start =======
@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    match = re.search(r"\d+", message.text)

    if not match:
        await message.reply_text(
            "🎬 أهلاً بك.\nتابع القناة: @Ramadan4kTV"
        )
        return

    v_id = int(match.group())

    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=ADMIN_CHANNEL,
            message_id=v_id
        )
    except:
        await message.reply_text("❌ الحلقة غير متوفرة.")

# ======= عند نشر حلقة جديدة في المصدر =======
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.video)
async def handle_new_video(client, message):
    v_id = str(message.id)

    # حفظ في DB
    db_query(
        "INSERT INTO episodes (v_id) VALUES (%s) ON CONFLICT (v_id) DO NOTHING",
        (v_id,),
        commit=True
    )

    # إنشاء زر المشاهدة
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "▶ مشاهدة الحلقة",
                url=f"https://t.me/{BOT_USERNAME}?start={v_id}"
            )
        ]]
    )

    # نشر في قناة النشر
    await client.send_video(
        chat_id=FORWARD_CHANNEL,
        video=message.video.file_id,
        caption=message.caption or "",
        reply_markup=keyboard
    )

    print(f"✅ تم نشر الحلقة {v_id} تلقائياً")

print("🚀 النظام يعمل من @Ramadan4kTV وينشر تلقائياً")
app.run()
