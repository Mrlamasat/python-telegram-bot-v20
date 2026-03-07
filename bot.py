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

# ===== [3] عرض الحلقة (الاعتماد الكلي على القاعدة للأزرار) =====
async def show_episode(client, message, v_id, edit=False):
    v_id_str = str(v_id)
    
    # 1. جلب بيانات الحلقة من القاعدة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id_str,))
    
    if not res:
        # إذا كانت الحلقة قديمة وغير مسجلة، نجلبها ونسجلها
        try:
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            raw_text = source_msg.caption if source_msg.caption else "مسلسل غير مسمى"
            # تنظيف الاسم: نأخذ السطر الأول ونحذف منه الأرقام
            title = re.sub(r"\d+", "", raw_text.split('\n')[0]).replace("حلقة", "").replace("الحلقة", "").strip()
            ep_num = 0 
            db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted')", (v_id_str, title, ep_num), fetch=False)
        except: return
    else:
        title, ep_num = res[0]

    # 2. جلب أزرار الحلقات المسجلة لهذا المسلسل (بناءً على الاسم والترتيب)
    all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    
    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep_num}</b>\n━━━━━━━━━━━━━━━"
    
    buttons = []
    row = []
    for ep_n, ep_vid in all_eps:
        # عرض رقم الحلقة أو ID إذا كان مجهولاً
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
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id_str,), fetch=False)
    except Exception as e: logger.error(f"Copy Error: {e}")

# ===== [4] معالجات الأوامر والنشر =====
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
    
    v_id, new_ep = cmd[1], cmd[2]
    if len(cmd) == 4:
        db_query("UPDATE videos SET ep_num = %s, title = %s WHERE v_id = %s", (new_ep, cmd[3], v_id), fetch=False)
    else:
        db_query("UPDATE videos SET ep_num = %s WHERE v_id = %s", (new_ep, v_id), fetch=False)
    await message.reply_text("✅ تم التحديث بنجاح.")

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
            v_id, title, p_id, ep = res[0][0], res[0][1], res[0][2], message.text
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep, v_id), fetch=False)
            me = await client.get_me()
            link = f"https://t.me/{me.username}?start={v_id}"
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep}]</b>\n<b>رابط المشاهدة:</b>\n{link}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=link)]]))

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1: await show_episode(client, message, message.command[1])
    else: await message.reply_text("👋 أهلاً بك يا محمد.")

if __name__ == "__main__":
    app.run()
