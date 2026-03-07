import os
import psycopg2
import logging
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات (Logs)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== [1] الإعدادات (تحويل المعرفات لأرقام صحيحة) =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
DATABASE_URL = os.environ.get("DATABASE_URL")

# المعرفات كأرقام (مهم جداً لتجنب Peer id invalid)
SOURCE_CHANNEL = int("-1003547072209")
PUBLIC_POST_CHANNEL = int("-1003554018307")
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN missing in Railway Variables!")
    exit(1)

# إنشاء العميل
app = Client(
    "railway_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# قائمة المسلسلات
OFFICIAL_SERIES = [
    'اولاد الراعي', 'كلهم بيحبو مودي', 'الست موناليزا', 'فن الحرب', 'افراج',
    'رامز ليفل الوحش', 'صحاب الارض', 'وننسى اللي كان', 'علي كلاي', 'عين سحريه', 
    'فخر الدلتا', 'الكينج', 'درش', 'راس الافعى', 'المداح', 'هي كيميا', 
    'سوا سوا', 'بيبو', 'النص الثاني', 'عرض وطلب', 'مولانا', 'فرصه اخيره', 
    'حكايه نرجس', 'اب ولكن', 'اللون الازرق', 'المتر سمير', 'بابا وماما جيران', 
    'قطر صغنطوط', 'ن النسوه'
]

# ===== [2] قاعدة البيانات =====
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

def clean_and_match(text):
    if not text: return None
    norm = text.replace(" ", "").replace("\n", "")
    for s in OFFICIAL_SERIES:
        if s.replace(" ", "") in norm: return s
    return None

# ===== [3] عرض الحلقة =====
async def show_episode(client, message, v_id):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (str(v_id),))
    if not res:
        target = message.message if hasattr(message, "data") else message
        await target.reply_text("❌ الحلقة غير موجودة حالياً.")
        return
    
    title, ep = res[0]
    db_query("INSERT INTO views_log (v_id) VALUES (%s)", (str(v_id),), fetch=False)
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (str(v_id),), fetch=False)

    # جلب الحلقات المجاورة
    prev_v = db_query("SELECT v_id FROM videos WHERE title=%s AND ep_num=%s", (title, ep-1))
    next_v = db_query("SELECT v_id FROM videos WHERE title=%s AND ep_num=%s", (title, ep+1))

    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>\n━━━━━━━━━━━━━━━"
    
    buttons = []
    nav_row = []
    if prev_v: nav_row.append(InlineKeyboardButton("⬅️ السابقة", callback_data=f"sh_{prev_v[0][0]}"))
    if next_v: nav_row.append(InlineKeyboardButton("التالية ➡️", callback_data=f"sh_{next_v[0][0]}"))
    if nav_row: buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    chat_id = message.message.chat.id if hasattr(message, "data") else message.chat.id
    
    try:
        # التأكد من تحويل v_id إلى int عند النسخ من القناة
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Copy Error: {e}")
        await client.send_message(chat_id, "⚠️ عذراً، تعذر جلب الفيديو من المصدر.")

@app.on_callback_query(filters.regex(r"^sh_"))
async def cb_handler(client, query):
    v_id = query.data.split("_")[1]
    await show_episode(client, query, v_id)
    await query.answer()

# ===== [4] الإحصائيات =====
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    u_count = db_query("SELECT COUNT(*) FROM users")[0][0]
    await message.reply_text(f"<b>📊 إحصائيات البوت</b>\n━━━━━━━━━━━━━━━\n👥 المستخدمين: {u_count}")

# ===== [5] نظام النشر التلقائي (المراقب) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def auto_post(client, message):
    # 1. فيديو
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
    
    # 2. بوستر
    elif message.photo:
        s_name = clean_and_match(message.caption)
        if s_name:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (s_name, message.photo.file_id, res[0][0]), fetch=False)

    # 3. رقم الحلقة
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (int(message.text), v_id), fetch=False)
            me = await client.get_me()
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{message.text}]</b>", reply_markup=markup)

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text(f"👋 أهلاً بك يا محمد. البوت يعمل وجاهز!")

if __name__ == "__main__":
    logger.info("🚀 البوت يعمل الآن...")
    app.run()
