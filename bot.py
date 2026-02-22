import asyncio
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# المتغيرات من GitHub Secrets
# =========================
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_CHANNEL = int(os.environ.get("ADMIN_CHANNEL"))
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SOURCE_CHANNEL = os.environ.get("SOURCE_CHANNEL", "@Ramadan4kTV")

# =========================
# تشغيل البوت
# =========================
app = Client(
    "mo_final_fix",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    session_string=SESSION_STRING,
    workers=20
)

# =========================
# دالات مساعدة
# =========================
def hide_text(text):
    if not text: return "‌"
    return "‌".join(list(text))

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

# =========================
# 1. سحب الحلقات تلقائيًا من المصدر
# =========================
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query(
        "INSERT INTO episodes (v_id, title, ep_num, duration, quality) VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (v_id) DO UPDATE SET duration=EXCLUDED.duration",
        (v_id, message.caption or f"فيديو {v_id}", 0, duration, "auto"),
        commit=True
    )
    print(f"✅ تم سحب حلقة جديدة: {v_id}")

# =========================
# 2. تحديث العناوين عند التعديل
# =========================
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def on_edit(client, message):
    v_id = str(message.id)
    db_query(
        "UPDATE episodes SET title=%s WHERE v_id=%s",
        (message.caption or f"فيديو {v_id}", v_id),
        commit=True
    )
    print(f"🔄 تم تحديث الحلقة: {v_id}")

# =========================
# 3. نظام مشاهدة الحلقة (زر)
# =========================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"🎬 أهلاً بك.\nتفضل بزيارة قناتنا: @MoAlmohsen")

    v_id = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
    if not data:
        return await message.reply_text("❌ الحلقة غير موجودة.")

    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    buttons = [
        [InlineKeyboardButton("▶ مشاهدة الحلقة", url=link)],
        [InlineKeyboardButton("🍿 المزيد من الحلقات", url="https://t.me/MoAlmohsen")]
    ]

    caption = f"🎬 {data['title']}\n🔢 حلقة رقم: {data['ep_num']}\n⚙️ الجودة: {data['quality']}"
    try:
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=caption,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        await message.reply_text(f"⚠️ حدث خطأ: {e}")

# =========================
# تشغيل البوت
# =========================
if __name__ == "__main__":
    print("🚀 البوت يعمل الآن على GitHub Actions...")
    app.run()
