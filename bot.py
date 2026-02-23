import os
import psycopg2
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus

# ===== إعدادات التنبيهات =====
logging.basicConfig(level=logging.INFO)

# ===== البيانات (Railway) =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHtplbFHhJ-4fatqVWXQowETrKg-u0cr0Q")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003790915936
FORCE_SUB_LINK = "https://t.me/+KyrbVyp0QCJhZGU8"
PUBLIC_POST_CHANNEL = "@MoAlmohsen"

app = Client("MoAlmohsenBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات المحدثة =====
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
            ep_num INTEGER,
            quality TEXT,
            duration TEXT
        )
    """, fetch=False)

init_db()

# دالة تشفير الاسم (Zero-Width Space) للإخفاء عن البحث
def encode_hidden(text):
    return "".join(["\u200b" + char for char in text])

# دالة جلب أزرار أرقام الحلقات فقط
async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    buttons = []
    row = []
    for v_id, ep_num in res:
        label = f"📍 {ep_num}" if v_id == current_v_id else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{(await app.get_me()).username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    return buttons

# ===== نظام استلام وإعداد المحتوى للأدمن =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    duration = f"{message.video.duration // 60} دقيقة" if message.video else "غير محدد"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id, "waiting", duration), fetch=False)
    await message.reply_text("✅ تم استلام الفيديو. أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل جديد"
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    # أزرار اختيار الجودة للأدمن
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]
    ])
    await message.reply_text(f"📌 البوستر: {title}\nاختر الجودة المطلوبة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, callback_query):
    _, q, v_id = callback_query.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await callback_query.message.edit_text(f"✅ تم اختيار الجودة: {q}\nأرسل الآن رقم الحلقة فقط:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, poster_id, quality, duration = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    bot_user = (await client.get_me()).username
    caption = f"🎬 **{title}**\n\nالحلقة: {ep_num}\nالجودة: {quality}\nالمده: {duration}\n\nنتمنى لكم مشاهده ممتعة."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{bot_user}?start={v_id}")]])
    
    await client.send_photo(PUBLIC_POST_CHANNEL, poster_id, caption=caption, reply_markup=markup)
    await message.reply_text("🚀 تم النشر بنجاح في القناة العامة.")

# ===== التحديث التلقائي عند تعديل الوصف (للحلقات القديمة) =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL))
async def sync_edits(client, message):
    v_id = str(message.id)
    if message.caption:
        db_query("UPDATE videos SET title=%s WHERE v_id=%s", (message.caption, v_id), fetch=False)
        await message.reply_text(f"🔄 تم تحديث العنوان للحلقة {v_id} تلقائياً.")

# ===== نظام المشاهدة للمستخدمين =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        await message.reply_text("أهلاً بك! استخدم الروابط من القناة.")
        return

    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if not res: return
    title, ep_num, quality, duration = res[0]

    # فحص الاشتراك
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
            raise UserNotParticipant
    except Exception:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=FORCE_SUB_LINK)],
                                      [InlineKeyboardButton("🔄 تحقق", callback_data=f"check_{v_id}")]])
        await message.reply_text("⚠️ يجب الانضمام للقناة لمشاهدة الحلقة.", reply_markup=markup)
        return

    await send_final_video(client, chat_id=message.chat.id, v_id=v_id, title=title, ep_num=ep_num, quality=quality, duration=duration)

@app.on_callback_query(filters.regex("^check_"))
async def check_user(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    try:
        m = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if m.status not in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
            res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
            await callback_query.message.delete()
            await send_final_video(client, user_id, v_id, *res[0])
        else:
            await callback_query.answer("❌ لم تشترك بعد!", show_alert=True)
    except:
        await callback_query.answer("❌ خطأ، تأكد من الاشتراك.")

async def send_final_video(client, chat_id, v_id, title, ep_num, quality, duration):
    # تشفير العنوان لمنع محركات البحث
    hidden_title = encode_hidden(title)
    ep_markup = await get_episodes_markup(title, v_id)
    
    caption = (f"الحلقة [{ep_num}]\n"
               f"الجودة [{quality}]\n"
               f"المده [{duration}]\n\n"
               f"{hidden_title}\n\n"
               f"نتمنى لكم مشاهده ممتعة.")
    
    await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(ep_markup))

if __name__ == "__main__":
    app.run()
