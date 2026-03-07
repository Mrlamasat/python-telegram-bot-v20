import os
import psycopg2
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== [1] الإعدادات (قراءة من Variables) =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

# إنشاء العميل مع دعم العمل في الذاكرة (مهم لريلواي)
app = Client("railway_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ===== [2] دالة قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return []

# ===== [3] عرض الحلقة (الجلب الذكي والتحديث التلقائي) =====
async def show_episode(client, message, v_id, edit=False):
    v_id_str = str(v_id)
    # البحث في القاعدة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id_str,))
    
    if not res:
        # ⚠️ إذا كانت الحلقة قديمة وغير مسجلة في القاعدة
        try:
            # جلب الرسالة من المصدر لاستخراج الاسم
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            title = source_msg.caption if source_msg.caption else "مسلسل قديم"
            ep_num = 0
            
            # تسجيلها فوراً في القاعدة لكي تظهر في الإحصائيات والأزرار
            db_query(
                "INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT DO NOTHING",
                (v_id_str, title, ep_num), fetch=False
            )
            logger.info(f"✅ تم تسجيل حلقة قديمة تلقائياً: {v_id_str}")
        except Exception as e:
            logger.error(f"Error fetching unknown v_id {v_id}: {e}")
            title, ep_num = "حلقة غير مسجلة", 0
    else:
        title, ep_num = res[0]

    # جلب الحلقات لتشكيل لوحة الـ 5 أزرار
    all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s ORDER BY ep_num ASC", (title,))
    
    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep_num}</b>\n━━━━━━━━━━━━━━━"
    
    buttons = []
    row = []
    for ep_n, ep_vid in all_eps:
        # تمييز الحلقة الحالية بنقاط
        btn_text = f"• {ep_n} •" if str(ep_vid) == v_id_str else str(ep_n)
        row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{ep_vid}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    chat_id = message.message.chat.id if hasattr(message, "data") else message.chat.id
    
    try:
        # التحديث في نفس المكان (حذف ثم إرسال)
        if edit and hasattr(message, "data"):
            await message.message.delete()
        
        # جلب النسخة من المصدر وإرسالها للمستخدم
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
        
        # تسجيل مشاهدة
        db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id_str,), fetch=False)
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id_str,), fetch=False)
    except Exception as e:
        logger.error(f"Copy Error: {e}")

@app.on_callback_query(filters.regex(r"^go_"))
async def nav_handler(client, query):
    v_id = query.data.split("_")[1]
    await show_episode(client, query, v_id, edit=True)
    await query.answer()

# ===== [4] نظام النشر الجديد (فيديو -> بوستر -> رقم) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
        await message.reply_text(f"✅ فيديو سجل: {message.id}")
    
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption, message.photo.file_id, res[0][0]), fetch=False)
            await message.reply_text(f"🖼️ تم ربط البوستر بـ: {message.caption}")
            
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]
            ep_num = int(message.text)
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
            
            me = await client.get_me()
            watch_link = f"https://t.me/{me.username}?start={v_id}"
            
            post_caption = (
                f"🎬 <b>{title}</b>\n"
                f"<b>الحلقة: [{ep_num}]</b>\n"
                f"<b>رابط المشاهدة:</b>\n{watch_link}"
            )
            
            await client.send_photo(
                PUBLIC_POST_CHANNEL, 
                p_id, 
                caption=post_caption, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ اضغط هنا للمشاهدة", url=watch_link)]])
            )
            await message.reply_text("🚀 تم النشر بالتنسيق الجديد!")

# ===== [5] أوامر البوت =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    # تسجيل المستخدم الجديد
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    
    if len(message.command) > 1:
        # جلب الحلقة سواء كانت قديمة أو جديدة
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text(f"👋 أهلاً بك يا محمد.\nالبوت جاهز لجلب الحلقات.")

if __name__ == "__main__":
    app.run()
