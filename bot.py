import os
import psycopg2
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

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
        logging.error(f"DB Error: {e}")
        return []

# ===== [3] عرض الحلقة (نفس المكان + 5 أزرار) =====
async def show_episode(client, message, v_id, edit=False):
    # جلب بيانات الحلقة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (str(v_id),))
    if not res: return
    
    title, current_ep = res[0]
    db_query("INSERT INTO views_log (v_id) VALUES (%s)", (str(v_id),), fetch=False)
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (str(v_id),), fetch=False)

    # جلب جميع حلقات المسلسل للوحة الأزرار
    all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s ORDER BY ep_num ASC", (title,))

    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {current_ep}</b>\n━━━━━━━━━━━━━━━"
    
    # بناء الأزرار (5 في كل سطر)
    buttons = []
    temp_row = []
    for ep_num, ep_v_id in all_eps:
        btn_text = f"• {ep_num} •" if ep_num == current_ep else str(ep_num)
        temp_row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{ep_v_id}"))
        if len(temp_row) == 5:
            buttons.append(temp_row)
            temp_row = []
    if temp_row: buttons.append(temp_row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    markup = InlineKeyboardMarkup(buttons)

    if edit and hasattr(message, "data"):
        # حذف الرسالة القديمة وإرسال الجديدة في نفس المكان لضمان تغيير الفيديو
        await message.message.delete()
        await client.copy_message(message.message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)
    else:
        # إرسال رسالة جديدة (في حالة /start)
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)

@app.on_callback_query(filters.regex(r"^go_"))
async def navigation_handler(client, query):
    v_id = query.data.split("_")[1]
    # نمرر edit=True لكي يعرف البوت أنه يجب استبدال الرسالة
    await show_episode(client, query, v_id, edit=True)
    await query.answer()

# ===== [4] نظام النشر والإحصائيات (كما في كودك المستقر) =====
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    u_count = db_query("SELECT COUNT(*) FROM users")[0][0]
    await message.reply_text(f"👥 عدد المشتركين: {u_count}")

@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption, message.photo.file_id, res[0][0]), fetch=False)
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]; ep_num = int(message.text)
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
            me = await client.get_me()
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep_num}]</b>", reply_markup=markup)

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text(f"👋 أهلاً بك يا محمد.")

if __name__ == "__main__":
    app.run()
