import os, re, psycopg2, logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209      # قناة الملفات
PUBLIC_POST_CHANNEL = -1003554018307  # قناة المنشورات
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

# تم إصلاح هذا السطر ليتوافق مع جميع إصدارات Pyrogram
app = Client("railway_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دالة قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close(); conn.close()
        return res
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return []

# ===== [3] نظام الربط الذكي (Search) =====
async def sync_episode_data(client, v_id):
    v_id = str(v_id)
    # البحث في القناة العامة عن المنشور الأصلي باستخدام المعرف
    async for message in client.search_messages(PUBLIC_POST_CHANNEL, query=f"start={v_id}"):
        if message.caption:
            lines = message.caption.split('\n')
            # استخراج الاسم: أول سطر
            title = lines[0].replace("🎬", "").strip()
            title = re.sub(r"\s+\.\s+", "", title).replace(".", "").strip()
            
            # استخراج الرقم: يبحث عن رقم بعد كلمة حلقة
            ep_match = re.search(r"(?:الحلقة|حلقة).*?(\d+)", message.caption)
            ep_num = int(ep_match.group(1)) if ep_match else 0
            
            db_query("""
                INSERT INTO videos (v_id, title, ep_num, status) 
                VALUES (%s, %s, %s, 'posted') 
                ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, status='posted'
            """, (v_id, title, ep_num), fetch=False)
            return title, ep_num
    return None, None

# ===== [4] عرض الحلقة ومعالجة الأزرار =====
async def show_episode(client, message, v_id, edit=False):
    v_id = str(v_id)
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    
    # إذا كانت البيانات ناقصة أو الحلقة جديدة، نستخدم الربط الذكي
    if not res or res[0][1] == 0:
        title, ep_num = await sync_episode_data(client, v_id)
        if not title: title, ep_num = "حلقة غير معرفة", 0
    else:
        title, ep_num = res[0]

    # جلب الحلقات (5 في كل سطر)
    all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    
    buttons = []
    row = []
    for e_num, e_vid in all_eps:
        btn_text = f"• {e_num} •" if str(e_vid) == v_id else str(e_num)
        row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{e_vid}"))
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    caption = f"📺 <b>{title}</b>\n🎬 <b>الحلقة رقم: {ep_num}</b>"
    chat_id = message.message.chat.id if hasattr(message, "data") else message.chat.id
    
    try:
        if edit and hasattr(message, "data"): await message.message.delete()
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Error: {e}")

# ===== [5] سيناريو المصدر (فيديو -> بوستر -> رقم) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        title = message.caption.strip() if message.caption else "غير مسمى"
        db_query("INSERT INTO videos (v_id, title, status) VALUES (%s, %s, 'waiting_poster') ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title", (str(message.id), title), fetch=False)
    
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status = 'waiting_poster' ORDER BY v_id DESC LIMIT 1")
        if res: db_query("UPDATE videos SET poster_id = %s, status = 'waiting_ep' WHERE v_id = %s", (message.photo.file_id, res[0][0]), fetch=False)
    
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status = 'waiting_ep' ORDER BY v_id DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]
            ep = int(message.text)
            db_query("UPDATE videos SET ep_num = %s, status = 'posted' WHERE v_id = %s", (ep, v_id), fetch=False)
            me = await client.get_me()
            link = f"https://t.me/{me.username}?start={v_id}"
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n📌 <b>الحلقة: {ep}</b>\n\n▶️ {link}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]]))

# ===== [6] التشغيل =====
@app.on_callback_query(filters.regex(r"^go_"))
async def navigation(c, q):
    await show_episode(c, q, q.data.split("_")[1], edit=True)
    await q.answer()

@app.on_message(filters.command("start") & filters.private)
async def start(c, m):
    if len(m.command) > 1: await show_episode(c, m, m.command[1])
    else: await m.reply_text("👋 النظام يعمل الآن يا محمد.")

if __name__ == "__main__":
    app.run()
