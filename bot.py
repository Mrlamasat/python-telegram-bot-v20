import os
import psycopg2
import re
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية (المعرفات الخاصة بك) =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# قناة المصدر (التي ترفع فيها الفيديوهات)
SOURCE_CHANNEL = -1003547072209

# قنوات النشر الخاصة (التي تحتوي على الأرقام الصحيحة)
PUBLISH_CHANNELS = [
    -1003554018307,
    -1003790915936,
    -1003678294148
]

BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== وظائف قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=10)
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
    logging.info("✅ قاعدة البيانات جاهزة")

# ===== دوال مساعدة =====
def encrypt_title(title):
    if not title: return "مسلسل"
    if len(title) <= 6: return title
    return title[:3] + "..." + title[-3:]

async def get_bot_username():
    me = await app.get_me()
    return me.username

async def is_valid_video(client, v_id):
    try:
        await client.get_messages(SOURCE_CHANNEL, int(v_id))
        return True
    except:
        return False

# ===== معالجات الأوامر (للمستخدم) =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        if len(message.command) > 1:
            v_id = message.command[1]
            if not await is_valid_video(client, v_id):
                return await message.reply_text("⚠️ هذه الحلقة غير متوفرة حالياً في المصدر.")
            await show_episode(client, message, v_id)
        else:
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("📢 قناة النشر", url=BACKUP_CHANNEL_LINK)]])
            await message.reply_text("👋 أهلاً بك يا محمد!\nاختر حلقة من القناة للمشاهدة.", reply_markup=markup)
    except Exception as e:
        logging.error(f"Start Error: {e}")

async def show_episode(client, message, current_vid):
    video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not video_info:
        return await message.reply_text("⚠️ لم يتم العثور على بيانات الحلقة.")
    
    title, current_ep = video_info[0]
    clean_title = title.strip()
    
    # تحديث المشاهدات
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    # جلب الحلقات المشابهة (مرتبة ومنع التكرار)
    all_episodes = db_query("""
        SELECT v_id, ep_num FROM videos 
        WHERE TRIM(title) = %s AND status = 'posted' AND ep_num > 0 
        ORDER BY ep_num ASC
    """, (clean_title,))
    
    username = await get_bot_username()
    btns, row, seen_eps = [], [], set()

    for vid, ep_num in all_episodes:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        
        label = f"✅ {ep_num}" if str(vid) == str(current_vid) else str(ep_num)
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{username}?start={vid}"))
        
        if len(row) == 5:
            btns.append(row)
            row = []
    
    if row: btns.append(row)
    btns.append([InlineKeyboardButton("📢 قناة النشر الأساسية", url=BACKUP_CHANNEL_LINK)])
    
    await client.copy_message(
        chat_id=message.chat.id,
        from_chat_id=SOURCE_CHANNEL,
        message_id=int(current_vid),
        caption=f"<b>📺 {encrypt_title(title)} - حلقة {current_ep}</b>",
        reply_markup=InlineKeyboardMarkup(btns),
        parse_mode=ParseMode.HTML
    )

# ===== أوامر الإدارة (ADMIN) =====
@app.on_message(filters.command("sync") & filters.private)
async def sync_channels(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    status_msg = await message.reply_text("🔄 جاري مزامنة الأرقام من قنوات النشر الخاصة...")
    updated = 0
    
    for channel_id in PUBLISH_CHANNELS:
        try:
            async for msg in client.get_chat_history(channel_id, limit=200):
                if msg.reply_markup and msg.caption:
                    url = msg.reply_markup.inline_keyboard[0][0].url
                    if "start=" not in url: continue
                    v_id = url.split("start=")[1]
                    
                    # استخراج الرقم من المنشور (القناة هي المرجع الصحيح)
                    match = re.search(r'\[(\d+)\]|حلقة\s*(\d+)', msg.caption, re.IGNORECASE)
                    if match:
                        correct_ep = int(match.group(1) or match.group(2))
                        db_query("UPDATE videos SET ep_num = %s, status = 'posted' WHERE v_id = %s", (correct_ep, v_id), fetch=False)
                        updated += 1
        except Exception as e:
            logging.error(f"Sync error in {channel_id}: {e}")

    await status_msg.edit_text(f"✅ تمت المزامنة!\nتم تصحيح {updated} حلقة بناءً على المنشورات.")

@app.on_message(filters.command("fix") & filters.private)
async def fix_database(client, message):
    if message.from_user.id != ADMIN_ID: return
    status_msg = await message.reply_text("🔍 جاري حذف الإدخالات غير الصالحة...")
    
    all_entries = db_query("SELECT v_id FROM videos WHERE status = 'posted'")
    deleted = 0
    for (v_id,) in all_entries:
        if not await is_valid_video(client, v_id):
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            deleted += 1
    
    await status_msg.edit_text(f"✅ تم التنظيف!\nتم حذف {deleted} إدخال ليس له فيديو في المصدر.")

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    res = db_query("SELECT COUNT(*), SUM(views) FROM videos")[0]
    await message.reply_text(f"📊 إحصائيات:\n• الحلقات: {res[0]}\n• المشاهدات: {res[1] or 0}")

# ===== معالج قناة المصدر (الرفع) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        if message.video or message.document:
            v_id = str(message.id)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id,), fetch=False)
            await message.reply_text("✅ تم استلام الفيديو!\nأرسل البوستر مع اسم المسلسل:")
        
        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id = res[0][0]
                db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption or "مسلسل", message.photo.file_id, v_id), fetch=False)
                await message.reply_text("📌 تم حفظ البوستر.\nأرسل الآن رقم الحلقة فقط:")
        
        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id, title, p_id = res[0]
                ep_num = int(message.text)
                db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
                
                # النشر في القناة الأولى (افتراضياً)
                username = await get_bot_username()
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=f"https://t.me/{username}?start={v_id}")]])
                await client.send_photo(PUBLISH_CHANNELS[0], p_id, caption=f"🎬 <b>{encrypt_title(title)}</b>\n\n<b>الحلقة: [{ep_num}]</b>", reply_markup=markup)
                await message.reply_text(f"✅ تم النشر بنجاح: حلقة {ep_num}")
    except Exception as e:
        logging.error(f"Source Error: {e}")

if __name__ == "__main__":
    init_database()
    app.run()
