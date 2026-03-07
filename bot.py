import os, psycopg2, logging, re, asyncio, time
from datetime import datetime
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# تصحيح رابط قاعدة البيانات لـ Railway
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("railway_bot_v2", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

SHOW_MORE_BUTTONS = False 

# ===== [2] دوال قاعدة البيانات =====
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

# ===== [3] استخراج البيانات =====
def extract_title_and_episode(text):
    if not text: return None, 0
    first_line = text.strip().split('\n')[0]
    patterns = [
        r'^(.+?)\s+(\d+)$', r'^(.+?)\s*-\s*(\d+)$',
        r'^(.+?)\s*:\s*(\d+)$', r'^(.+?)\s*:\s*\[(\d+)\]$',
        r'^(.+?)\s+\[(\d+)\]$', r'^(.+?)\s*[#](\d+)$'
    ]
    for pattern in patterns:
        match = re.search(pattern, first_line, re.UNICODE)
        if match:
            return match.group(1).strip(), int(match.group(2))
    return first_line[:100], 0

# ===== [4] معالج التحديث الفوري (إضافة وتعديل) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def handle_updates(client, message):
    try:
        raw_text = message.caption or message.text
        if not raw_text: return
        
        v_id = str(message.id)
        title, ep_num = extract_title_and_episode(raw_text)
        
        if ep_num > 0:
            # تحديث أو إضافة لقاعدة البيانات
            db_query("""
                INSERT INTO videos (v_id, title, ep_num, status) 
                VALUES (%s, %s, %s, 'posted')
                ON CONFLICT (v_id) DO UPDATE SET 
                title = EXCLUDED.title,
                ep_num = EXCLUDED.ep_num,
                status = 'updated'
            """, (v_id, title, ep_num), fetch=False)
            
            # إرسال إشعار للمشرف
            action_text = "🔄 تم تحديث رقم الحلقة" if message.edit_date else "🆕 تم إضافة حلقة جديدة"
            await client.send_message(
                ADMIN_ID,
                f"⚡ **{action_text}**\n\n"
                f"🎬 المسلسل: {title}\n"
                f"🔢 الرقم الجديد: {ep_num}\n"
                f"🆔 المعرف: `{v_id}`"
            )
    except Exception as e:
        logging.error(f"Update Error: {e}")

# ===== [5] عرض الحلقة للمستخدم =====
async def show_episode(client, message, v_id):
    try:
        db_data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        if not db_data:
            return await message.reply_text("❌ الحلقة غير مسجلة في النظام")
        
        title, ep = db_data[0]
        keyboard = []
        
        if SHOW_MORE_BUTTONS:
            other_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s AND ep_num > 0 AND v_id != %s ORDER BY ep_num ASC", (title, v_id))
            if other_eps:
                row = []
                me = await client.get_me()
                for o_ep, o_vid in other_eps:
                    row.append(InlineKeyboardButton(str(o_ep), url=f"https://t.me/{me.username}?start={o_vid}"))
                    if len(row) == 5:
                        keyboard.append(row)
                        row = []
                if row: keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        await client.copy_message(
            message.chat.id, SOURCE_CHANNEL, int(v_id),
            caption=f"<b>{title} - الحلقة {ep}</b>",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # تسجيل المشاهدة (مع التأكد من وجود العمود)
        db_query("INSERT INTO views_log (v_id, user_id) VALUES (%s, %s)", (v_id, message.from_user.id), fetch=False)
    except Exception as e:
        logging.error(f"Show Error: {e}")

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    db_query("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (user_id, message.from_user.username), fetch=False)
    
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المشاهدة.")

# ===== [6] تهيئة قاعدة البيانات =====
def init_database():
    # إنشاء الجداول
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS views_log (id SERIAL PRIMARY KEY, v_id TEXT, user_id BIGINT, viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    
    # التأكد من وجود عمود user_id (حل مشكلة Error Logs)
    try:
        db_query("ALTER TABLE views_log ADD COLUMN IF NOT EXISTS user_id BIGINT", fetch=False)
    except: pass
    print("✅ Database Ready")

if __name__ == "__main__":
    init_database()
    print("🚀 Bot is running...")
    app.run()
