import os
import psycopg2
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== إعدادات التسجيل =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== المتغيرات الأساسية (تأكد من مطابقتها في Railway) =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0")
DATABASE_URL = os.environ.get("DATABASE_URL") 

# إعدادات القنوات حسب تحديدك الأخير
SOURCE_CHANNEL = -1003790915936  # القناة التي ترفع فيها الحلقات
FORCE_SUB_ID = -1002222222222    # !!! يجب استبدال هذا برقم الـ ID لقناة الاشتراك الإجباري الخاصة
FORCE_SUB_LINK = "https://t.me/+KyrbVyp0QCJhZGU8"
DESTINATION_CHANNEL = "@MoAlmohsen" # قناة النشر العامة

app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== دالة قاعدة البيانات =====
def db_query(query, params=(), commit=True, fetch=True):
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(query, params)
    if commit: conn.commit()
    res = cur.fetchall() if fetch else None
    cur.close()
    conn.close()
    return res

# ===== دالة التحقق من الاشتراك الإجباري =====
async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_ID, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except UserNotParticipant:
        return False
    except Exception:
        return True 
    return False

# ===== استقبال المحتوى من قناة المصدر (الرفع) =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET status = 'waiting'", (v_id, "waiting"), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو من المصدر.\nأرسل الآن البوستر مع اسم المسلسل.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل جديد"
    db_query("UPDATE videos SET title = %s, poster_id = %s, status = 'awaiting_ep' WHERE v_id = %s",
               (title, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 تم حفظ البوستر لـ **{title}**\n🔢 أرسل رقم الحلقة:")

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
    
    # النشر في قناة @MoAlmohsen
    try:
        caption = f"🎬 **{title}**\n🔹 **الحلقة رقم:** {ep_num}\n\n📥 **لمشاهدة الحلقة اضغط على الزر أدناه:**"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])
        await client.send_photo(chat_id=DESTINATION_CHANNEL, photo=poster_id, caption=caption, reply_markup=reply_markup)
        await message.reply_text(f"🚀 تم النشر بنجاح في {DESTINATION_CHANNEL}")
    except Exception as e:
        await message.reply_text(f"⚠️ فشل النشر: {e}")

# ===== نظام المشاهدة =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # التحقق من الاشتراك في القناة الإجبارية
    if not await check_subscription(client, user_id):
        buttons = [[InlineKeyboardButton("📢 اشترك هنا أولاً", url=FORCE_SUB_LINK)]]
        if len(message.command) > 1:
            buttons.append([InlineKeyboardButton("🔄 تحقق ثانية", url=f"https://t.me/{(await client.get_me()).username}?start={message.command[1]}")])
        
        await message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if len(message.command) <= 1:
        await message.reply_text(f"أهلاً بك يا محمد! أرسل رابط الحلقة للمشاهدة.")
        return

    v_id = message.command[1]
    try:
        # إرسال الفيديو من القناة المصدر (التي ترفع فيها)
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id))
    except Exception as e:
        await message.reply_text(f"❌ خطأ في جلب الفيديو: {e}")

if __name__ == "__main__":
    app.run()
