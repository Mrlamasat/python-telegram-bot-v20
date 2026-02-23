import os
import psycopg2
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Callback_query
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus

# ===== 1. إعدادات التنبيهات والأخطاء =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== 2. جلب البيانات من متغيرات البيئة =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHtplbFHhJ-4fatqVWXQowETrKg-u0cr0Q")
DATABASE_URL = os.environ.get("DATABASE_URL")

# إعدادات القنوات
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003790915936  # معرف القناة المطلوب الاشتراك بها
FORCE_SUB_LINK = "https://t.me/+KyrbVyp0QCJhZGU8"
PUBLIC_POST_CHANNEL = "@MoAlmohsen"

app = Client("MoAlmohsenBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== 3. إدارة قاعدة البيانات (PostgreSQL) =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

def init_db():
    try:
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
        logging.info("✅ Database initialized successfully.")
    except Exception as e:
        logging.error(f"❌ Database init error: {e}")

# تشغيل تهيئة القاعدة عند البدء
init_db()

# ===== 4. الدوال المساعدة =====

def encode_hidden(text):
    """إخفاء النص عن محركات البحث باستخدام مسافات غير مرئية"""
    if not text: return ""
    return "".join(["\u200b" + char for char in text])

async def get_episodes_markup(title, current_v_id):
    """إنشاء أزرار أرقام الحلقات لنفس المسلسل"""
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return None
    
    buttons, row = [], []
    bot_info = await app.get_me()
    
    for v_id, ep_num in res:
        label = f"📍 {ep_num}" if v_id == current_v_id else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    return buttons

async def is_subscribed(client, user_id):
    """فحص الاشتراك الإجباري (يسمح للمشرفين والمالك بالمرور)"""
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        allowed = [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        if member.status in allowed:
            return True
        return False
    except (UserNotParticipant, Exception):
        return False

# ===== 5. نظام المزامنة (للحلقات القديمة) =====

@app.on_edited_message(filters.chat(SOURCE_CHANNEL))
async def sync_old_videos(client, message):
    """يتم تفعيلها عند تعديل وصف فيديو قديم في قناة الرفع"""
    if message.video or message.document:
        v_id = str(message.id)
        title = message.caption or "مسلسل جديد"
        dur_sec = message.video.duration if message.video else 0
        duration = f"{dur_sec // 60} دقيقة" if dur_sec > 0 else "غير محدد"
        
        db_query("""
            INSERT INTO videos (v_id, title, status, duration, quality, ep_num) 
            VALUES (%s, %s, %s, %s, %s, %s) 
            ON CONFLICT (v_id) DO UPDATE SET title=%s, status='posted'
        """, (v_id, title, 'posted', duration, 'HD', 1, title), fetch=False)
        
        await message.reply_text(f"🔄 تم سحب الحلقة {v_id} وتخزينها في القاعدة بنجاح!")

# ===== 6. دورة النشر الجديدة (الأدمن) =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    dur = f"{message.video.duration // 60} دقيقة" if message.video else "غير محدد"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id, "waiting", dur), fetch=False)
    await message.reply_text("✅ تم استلام الفيديو. أرسل الآن البوستر مع اسم المسلسل في الوصف.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل جديد"
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"),
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
    ]])
    await message.reply_text(f"📌 البوستر: {title}\nاختر جودة العرض:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, callback_query):
    _, q, v_id = callback_query.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await callback_query.message.edit_text(f"✅ الجودة المختارة: {q}\nأرسل الآن رقم الحلقة فقط:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    
    v_id, title, poster_id, quality, duration = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    bot_info = await client.get_me()
    caption = f"🎬 **{title}**\n\nالحلقة [{ep_num}]\nالجودة [{quality}]\nالمده [{duration}]\n\nنتمنى لكم مشاهده ممتعة."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{bot_info.username}?start={v_id}")]])
    
    await client.send_photo(PUBLIC_POST_CHANNEL, poster_id, caption=caption, reply_markup=markup)
    await message.reply_text("🚀 تم النشر بنجاح في القناة العامة.")

# ===== 7. نظام المشاهدة للمستخدمين =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا محمد! استخدم الروابط في القناة للمشاهدة.")
        return

    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    
    if not res:
        await message.reply_text("❌ عذراً، هذه الحلقة غير متوفرة حالياً.\n(للأدمن: قم بتعديل وصف الحلقة في قناة الرفع لمزامنتها)")
        return

    if not await is_subscribed(client, message.from_user.id):
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 اشترك هنا أولاً", url=FORCE_SUB_LINK)],
            [InlineKeyboardButton("🔄 تحقق ثانية", callback_data=f"chk_{v_id}")]
        ])
        await message.reply_text("⚠️ **يجب الانضمام للقناة لمشاهدة الحلقة.**", reply_markup=markup)
        return

    await send_video_final(client, message.chat.id, v_id, *res[0])

@app.on_callback_query(filters.regex("^chk_"))
async def check_callback(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    if await is_subscribed(client, callback_query.from_user.id):
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res:
            await callback_query.message.delete()
            await send_video_final(client, callback_query.from_user.id, v_id, *res[0])
    else:
        await callback_query.answer("❌ لم تشترك بعد في القناة!", show_alert=True)

async def send_video_final(client, chat_id, v_id, title, ep, q, dur):
    """إرسال الفيديو مع الأزرار المتسلسلة وتشفير الاسم"""
    markup_btns = await get_episodes_markup(title, v_id)
    hidden_title = encode_hidden(title)
    
    caption = (f"الحلقة [{ep}]\n"
               f"الجودة [{q}]\n"
               f"المده [{dur}]\n\n"
               f"{hidden_title}\n\n"
               f"نتمنى لكم مشاهده ممتعة.")
    
    try:
        await client.copy_message(
            chat_id=chat_id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=caption,
            reply_markup=InlineKeyboardMarkup(markup_btns) if markup_btns else None
        )
    except Exception as e:
        await client.send_message(chat_id, f"❌ حدث خطأ: {e}")

if __name__ == "__main__":
    app.run()
