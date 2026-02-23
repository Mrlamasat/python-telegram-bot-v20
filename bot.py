import os
import psycopg2
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== Logging =====
logging.basicConfig(level=logging.INFO)

# ===== Environment Variables =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = "@MoAlmohsen"
FORCE_SUB_LINK = "https://t.me/MoAlmohsen"
PUBLIC_POST_CHANNEL = "@MoAlmohsen"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Database =====
def db_query(query, params=(), fetch=True):
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    result = cur.fetchall() if fetch else None
    cur.close()
    conn.close()
    return result

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            status TEXT,
            ep_num INTEGER
        )
    """, fetch=False)

init_db()

# ===== Force Subscription Check =====
async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)

        if member.status in ["left", "kicked"]:
            return False

        return True

    except UserNotParticipant:
        return False

    except Exception as e:
        logging.error(f"Subscription error: {e}")
        return False

# ===== Receive Video =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    db_query(
        "INSERT INTO videos (v_id, status) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting'",
        (v_id, "waiting"),
        fetch=False
    )
    await message.reply_text("✅ تم استلام الفيديو.\nأرسل الآن البوستر مع اسم المسلسل في الوصف.")

# ===== Receive Poster =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res:
        return

    v_id = res[0][0]
    title = message.caption or "مسلسل جديد"

    db_query(
        "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s",
        (title, message.photo.file_id, v_id),
        fetch=False
    )

    await message.reply_text("📌 تم حفظ البوستر.\nأرسل رقم الحلقة فقط.")

# ===== Receive Episode Number =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep(client, message):
    if not message.text.isdigit():
        return

    res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res:
        return

    v_id, title, poster_id = res[0]
    ep_num = int(message.text)

    db_query(
        "UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s",
        (ep_num, v_id),
        fetch=False
    )

    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"

    caption = f"🎬 {title}\n🔹 الحلقة رقم: {ep_num}\n\nاضغط الزر لمشاهدة الحلقة:"
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]]
    )

    await client.send_photo(
        chat_id=PUBLIC_POST_CHANNEL,
        photo=poster_id,
        caption=caption,
        reply_markup=markup
    )

    await message.reply_text("🚀 تم النشر بنجاح.")

# ===== Start Command =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id

    if len(message.command) < 2:
        await message.reply_text("أهلاً بك 👋\nاستخدم رابط الحلقات من القناة.")
        return

    v_id = message.command[1]

    if not await check_subscription(client, user_id):
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك في القناة", url=FORCE_SUB_LINK)],
            [InlineKeyboardButton("🔄 تحقق", callback_data=f"recheck_{v_id}")]
        ])
        await message.reply_text(
            "⚠️ يجب الاشتراك في القناة أولاً لمشاهدة الحلقة.",
            reply_markup=markup
        )
        return

    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id))

# ===== Recheck Button =====
@app.on_callback_query(filters.regex("^recheck_"))
async def recheck(client, callback_query):
    user_id = callback_query.from_user.id
    v_id = callback_query.data.split("_")[1]

    if not await check_subscription(client, user_id):
        await callback_query.answer("❌ لم يتم الاشتراك بعد", show_alert=True)
        return

    await callback_query.answer("✅ تم التحقق")
    await client.copy_message(callback_query.message.chat.id, SOURCE_CHANNEL, int(v_id))

# ===== Run =====
if __name__ == "__main__":
    app.run()
