import os
import psycopg2
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_stable", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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
        logging.error(f"Database Error: {e}")
        return []

def init_database():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            ep_num INTEGER,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            last_view TIMESTAMP
        )
    """, fetch=False)
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            joined_at TIMESTAMP DEFAULT NOW()
        )
    """, fetch=False)

# ===== [3] دوال المساعدة والتشفير =====
def encrypt_title(title, level=2):
    if not title: return "مسلسل"
    title = title.strip()
    if len(title) <= 4: return title[:2] + "••"
    return title[:2] + "•••" + title[-2:]

async def is_valid_video(client, v_id):
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        return msg and not msg.empty
    except: return False

# ===== [4] نظام الأزرار والعرض =====
async def get_episodes_markup(client, title, current_v_id):
    all_entries = db_query("""
        SELECT v_id, ep_num FROM videos 
        WHERE title = %s AND status = 'posted' 
        ORDER BY ep_num ASC
    """, (title,))
    
    valid_episodes = {}
    for v_id, ep_num in all_entries:
        if ep_num in valid_episodes: continue
        if await is_valid_video(client, v_id):
            valid_episodes[ep_num] = v_id
        else:
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)

    keyboard = []
    row = []
    sorted_eps = sorted(valid_episodes.items()) 
    for ep_num, v_id in sorted_eps:
        btn_text = f"• {ep_num} •" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{v_id}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔗 اضغط هنا للاشتراك بالقناه الإحتياطيه", url=BACKUP_CHANNEL_LINK)])
    return InlineKeyboardMarkup(keyboard)

async def show_episode(client, message, current_vid, is_callback=False):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not res: return

    title, current_ep = res[0]
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    # تم حذف الجملة التي لم تطلبها
    caption = (
        f"<b>📺 {encrypt_title(title)}</b>\n"
        f"<b>🎬 الحلقة رقم: {current_ep}</b>\n"
        f"━━━━━━━━━━━━━━━"
    )
    
    markup = await get_episodes_markup(client, title, current_vid)

    if is_callback:
        try: await message.delete()
        except: pass
        
    await client.copy_message(
        chat_id=message.chat.id,
        from_chat_id=SOURCE_CHANNEL,
        message_id=int(current_vid),
        caption=caption,
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )

# ===== [5] المعالجات =====

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 اضغط هنا للاشتراك بالقناه الإحتياطيه", url=BACKUP_CHANNEL_LINK)]])
        await message.reply_text(f"👋 أهلاً بك يا محمد في بوت المسلسلات!\nاختر حلقة من القناة للمشاهدة.", reply_markup=markup)

@app.on_callback_query(filters.regex("^go_"))
async def handle_navigation(client, callback_query):
    target_vid = callback_query.data.split("_")[1]
    await show_episode(client, callback_query.message, target_vid, is_callback=True)

# ===== [6] نظام النشر المطور =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source_auto(client, message):
    try:
        if message.video or message.document:
            v_id = str(message.id)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (v_id,), fetch=False)
            await message.reply_text(f"✅ تم استلام الفيديو `{v_id}`\nالآن أرسل البوستر.")

        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id = res[0][0]
                title = message.caption or "مسلسل"
                db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
                await message.reply_text(f"📌 تم حفظ البوستر لـ: {title}\nأرسل رقم الحلقة.")

        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id, title, p_id = res[0]
                ep_num = int(message.text)
                db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
                me = await client.get_me()
                pub_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ اضغط هنا لمشاهدة الحلقة كاملة", url=f"https://t.me/{me.username}?start={v_id}")]])
                await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{encrypt_title(title)}</b>\n<b>الحلقة: [{ep_num}]</b>", reply_markup=pub_markup)
                await message.reply_text(f"🚀 تم النشر: {title} - حلقة {ep_num}")
    except Exception as e: logging.error(f"Error: {e}")

# ===== [7] الإحصائيات =====
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    u_count = db_query("SELECT COUNT(*) FROM users")[0][0]
    v_total = db_query("SELECT SUM(views) FROM videos")[0][0] or 0
    v_daily = db_query("SELECT SUM(views) FROM videos WHERE last_view >= NOW() - INTERVAL '1 day'")[0][0] or 0
    v_count = db_query("SELECT COUNT(*) FROM videos WHERE status='posted'")[0][0]
    
    report = (
        "<b>📊 إحصائيات البوت (محمد المحسن)</b>\n"
        "━━━━━━━━━━━━━━━\n"
        f"<b>👥 المشتركين:</b> <code>{u_count}</code>\n"
        f"<b>🎬 الحلقات:</b> <code>{v_count}</code>\n"
        "━━━━━━━━━━━━━━━\n"
        f"<b>🔥 مشاهدات اليوم:</b> <code>{v_daily}</code>\n"
        f"<b>👁️ إجمالي المشاهدات:</b> <code>{v_total:,}</code>\n"
    )
    await message.reply_text(report, parse_mode=ParseMode.HTML)

if __name__ == "__main__":
    init_database()
    app.run()
