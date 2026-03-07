import os
import psycopg2
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

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

# ===== [2] عرض الحلقة (نفس المكان + 5 أزرار) =====
async def show_episode(client, message, v_id, edit=False):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (str(v_id),))
    if not res: return
    
    title, current_ep = res[0]
    db_query("INSERT INTO views_log (v_id) VALUES (%s)", (str(v_id),), fetch=False)
    
    # جلب جميع الحلقات لعمل لوحة الـ 5 أزرار
    all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s ORDER BY ep_num ASC", (title,))
    
    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {current_ep}</b>\n━━━━━━━━━━━━━━━"
    
    buttons = []
    row = []
    for ep_n, ep_vid in all_eps:
        btn_text = f"• {ep_n} •" if str(ep_vid) == str(v_id) else str(ep_n)
        row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{ep_vid}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    chat_id = message.message.chat.id if hasattr(message, "data") else message.chat.id
    
    try:
        if edit and hasattr(message, "data"):
            await message.message.delete()
        
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logging.error(f"Copy Error: {e}")

@app.on_callback_query(filters.regex(r"^go_"))
async def navigation_handler(client, query):
    v_id = query.data.split("_")[1]
    await show_episode(client, query, v_id, edit=True)
    await query.answer()

# ===== [3] نظام النشر بالتنسيق الجديد =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    # 1. استلام الفيديو
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
        await message.reply_text(f"✅ فيديو مسجل: {message.id}")
    
    # 2. استلام البوستر
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption, message.photo.file_id, res[0][0]), fetch=False)
            await message.reply_text(f"🖼️ تم ربط البوستر لـ: {message.caption}")
            
    # 3. استلام الرقم والنشر بالتنسيق المطلوب
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]
            ep_num = int(message.text)
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
            
            me = await client.get_me()
            watch_link = f"https://t.me/{me.username}?start={v_id}"
            
            # التنسيق الذي طلبته يا محمد
            post_caption = (
                f"🎬 <b>{title}</b>\n"
                f"<b>الحلقة: [{ep_num}]</b>\n"
                f"<b>رابط المشاهدة:</b>\n{watch_link}"
            )
            
            # النشر في القناة العامة
            await client.send_photo(
                PUBLIC_POST_CHANNEL, 
                p_id, 
                caption=post_caption, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ اضغط هنا للمشاهدة", url=watch_link)]])
            )
            await message.reply_text("🚀 تم النشر بالتنسيق الجديد!")

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text(f"👋 أهلاً بك يا محمد. البوت يعمل وجاهز.")

if __name__ == "__main__":
    app.run()
