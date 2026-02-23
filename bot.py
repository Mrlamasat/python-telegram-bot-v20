import os
import psycopg2
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, PeerIdInvalid

# ===== إعدادات التنبيهات والأخطاء =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== سحب البيانات من متغيرات Railway =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHtplbFHhJ-4fatqVWXQowETrKg-u0cr0Q")
DATABASE_URL = os.environ.get("DATABASE_URL")

# إعدادات القنوات بناءً على مدخلاتك
SOURCE_CHANNEL = int(os.environ.get("SOURCE_CHANNEL", -1003547072209))
FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", -1003790915936))
FORCE_SUB_LINK = "https://t.me/+KyrbVyp0QCJhZGU8"
PUBLIC_POST_CHANNEL = os.environ.get("PUBLIC_POST_CHANNEL", "@MoAlmohsen")

app = Client("MoAlmohsenBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات (PostgreSQL) =====
def db_query(query, params=(), commit=True, fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if commit: conn.commit()
        res = cur.fetchall() if fetch else None
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"Database Error: {e}")
        return []

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS videos 
                (v_id TEXT PRIMARY KEY, title TEXT, poster_id TEXT, status TEXT, ep_num INTEGER)''', commit=True, fetch=False)

# تشغيل قاعدة البيانات عند البدء
init_db()

# ===== دالة فحص الاشتراك الإجباري =====
async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except (UserNotParticipant, PeerIdInvalid):
        return False
    except Exception as e:
        logging.error(f"Sub Check Error: {e}")
        return True # تمرير في حال وجود خطأ تقني غير معروف
    return False

# ===== 1. استلام المحتوى من قناة الرفع =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET status = 'waiting'", (v_id, "waiting"), fetch=False)
    await message.reply_text("✅ **تم استلام الفيديو.**\nالآن أرسل البوستر (صورة) واكتب اسم المسلسل في الوصف (Caption).")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل جديد"
    db_query("UPDATE videos SET title = %s, poster_id = %s, status = 'awaiting_ep' WHERE v_id = %s",
               (title, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 **تم حفظ البوستر:** {title}\n🔢 الآن أرسل رقم الحلقة فقط:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep_number(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status = 'awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    
    v_id, title, poster_id = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num = %s, status = 'posted' WHERE v_id = %s", (ep_num, v_id), fetch=False)
    
    bot_info = await client.get_me()
    watch_link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    # النشر في القناة العامة
    try:
        caption = f"🎬 **{title}**\n🔹 **الحلقة رقم:** {ep_num}\n\n📥 **لمشاهدة الحلقة اضغط على الزر أدناه:**"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=poster_id, caption=caption, reply_markup=reply_markup)
        await message.reply_text(f"🚀 **تم النشر بنجاح في {PUBLIC_POST_CHANNEL}**")
    except Exception as e:
        await message.reply_text(f"⚠️ **فشل النشر التلقائي:** {e}\nرابط الحلقة: {watch_link}")

# ===== 2. نظام التشغيل للمستخدمين =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # التحقق من الاشتراك
    if not await check_subscription(client, user_id):
        btn = [[InlineKeyboardButton("📢 اشترك هنا أولاً", url=FORCE_SUB_LINK)]]
        if len(message.command) > 1:
            btn.append([InlineKeyboardButton("🔄 تحقق ثانية", url=f"https://t.me/{(await client.get_me()).username}?start={message.command[1]}")])
        await message.reply_text("⚠️ **عذراً، يجب الانضمام للقناة لمشاهدة الحلقة.**", reply_markup=InlineKeyboardMarkup(btn))
        return

    # إرسال الحلقة
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            # النسخ من قناة الرفع
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id))
        except Exception as e:
            await message.reply_text(f"❌ **عذراً، حدث خطأ أثناء جلب الفيديو:**\n{e}")
    else:
        await message.reply_text(f"أهلاً بك يا محمد! استخدم الروابط في القناة للمشاهدة.")

if __name__ == "__main__":
    app.run()
