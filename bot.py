import os
import re
import psycopg2
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

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

# ===== [3] معالج استخراج البيانات الذكي =====
def extract_data(raw_text):
    # 1. استخراج رقم الحلقة (يبحث عن الرقم المرتبط بكلمة حلقة حصراً)
    # يغطي: الحلقة: [16] ، الحلقة [11] ، الحلقة رقم: 7 ، الحلقة 2
    ep_match = re.search(r"(?:الحلقة|حلقة)(?:\s+رقم)?[:\s!]*\[?(\d+)\]?", raw_text)
    ep_num = int(ep_match.group(1)) if ep_match else 0
    
    # 2. استخراج الاسم وتنظيفه
    lines = raw_text.split('\n')
    title = "مسلسل غير مسمى"
    for line in lines:
        clean_line = line.strip()
        if not clean_line: continue
        # نأخذ السطر الذي يحتوي على 🎬 أو أول سطر لا يحتوي على كلمة "حلقة" أو "مدة"
        if "🎬" in clean_line and "الحلقة" not in clean_line:
            title = clean_line.replace("🎬", "").strip()
            break
        elif "الحلقة" not in clean_line and "المدة" not in clean_line and "الجودة" not in clean_line:
            title = clean_line.strip()
            break
            
    # تنظيف العنوان من الحروف المقطعة (و . ن . ن . س . ى -> وننسى)
    title = re.sub(r"\s+\.\s+", "", title) # حذف " . "
    title = title.replace(".", "").strip()
    
    return title, ep_num

# ===== [4] عرض الحلقة =====
async def show_episode(client, message, v_id, edit=False):
    v_id_str = str(v_id)
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id_str,))
    
    if not res:
        try:
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            raw_text = source_msg.caption if source_msg.caption else "مسلسل مجهول"
            title, ep_num = extract_data(raw_text)
            
            db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted')", 
                     (v_id_str, title, ep_num), fetch=False)
        except: return
    else:
        title, ep_num = res[0]

    all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    
    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep_num}</b>\n━━━━━━━━━━━━━━━"
    
    buttons = []
    row = []
    for ep_n, ep_vid in all_eps:
        display = str(ep_n) if ep_n != 0 else f"?({ep_vid})"
        btn_text = f"• {display} •" if str(ep_vid) == v_id_str else display
        row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{ep_vid}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    chat_id = message.message.chat.id if hasattr(message, "data") else message.chat.id
    try:
        if edit and hasattr(message, "data"): await message.message.delete()
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e: logger.error(f"Copy Error: {e}")

# ===== [5] الأوامر والنشر =====
@app.on_callback_query(filters.regex(r"^go_"))
async def nav_handler(client, query):
    v_id = query.data.split("_")[1]
    await show_episode(client, query, v_id, edit=True)
    await query.answer()

@app.on_message(filters.command("set") & filters.private)
async def set_data(client, message):
    if message.from_user.id != ADMIN_ID: return
    cmd = message.text.split(maxsplit=3)
    if len(cmd) < 3: return await message.reply_text("الصيغة: `/set ID الرقم` أو `/set ID الرقم الاسم`")
    if len(cmd) == 4:
        db_query("UPDATE videos SET ep_num = %s, title = %s WHERE v_id = %s", (cmd[2], cmd[3], cmd[1]), fetch=False)
    else:
        db_query("UPDATE videos SET ep_num = %s WHERE v_id = %s", (cmd[2], cmd[1]), fetch=False)
    await message.reply_text("✅ تم التحديث.")

@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res: db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption, message.photo.file_id, res[0][0]), fetch=False)
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, raw_title, p_id = res[0]
            # استخدام المعالج الذكي للنشر الجديد أيضاً
            title, _ = extract_data(raw_title)
            ep = message.text
            db_query("UPDATE videos SET ep_num=%s, title=%s, status='posted' WHERE v_id=%s", (ep, title, v_id), fetch=False)
            me = await client.get_me()
            link = f"https://t.me/{me.username}?start={v_id}"
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep}]</b>\n<b>رابط المشاهدة:</b>\n{link}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=link)]]))

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1: await show_episode(client, message, message.command[1])
    else: await message.reply_text("👋 أهلاً بك يا محمد.")

if __name__ == "__main__":
    app.run()
