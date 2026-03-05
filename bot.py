import os
import psycopg2
import logging
import re
import asyncio
import time
import random
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

# ===== إعداد السجلات =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)

# ===== الإعدادات الأساسية =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003790915936
FORCE_SUB_LINK = "https://t.me/+nLtMePUz6lw3YzBk"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, sleep_threshold=60)

# ===== قاعدة البيانات المطورة =====
def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()

def init_database():
    # إنشاء الجدول بالهيكلة الصحيحة
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            video_quality TEXT DEFAULT 'HD',
            duration TEXT DEFAULT '00:00:00',
            poster_id TEXT,
            poster_caption TEXT,
            raw_caption TEXT,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # محاولة إضافة العمود في حال كان الجدول قديماً (لتجنب خطأ Column Not Found)
    try:
        db_query("ALTER TABLE videos ADD COLUMN IF NOT EXISTS video_quality TEXT DEFAULT 'HD'", fetch=False)
        db_query("ALTER TABLE videos ADD COLUMN IF NOT EXISTS poster_caption TEXT", fetch=False)
    except: pass
    
    logging.info("✅ تم تحديث قاعدة البيانات بنجاح")

# ===== دوال المساعدة =====
def clean_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'(?:الحلقة|حلقة|#)\s*\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep_num(text):
    match = re.search(r'(?:الحلقة|حلقة|#)\s*(\d+)', text or '', re.IGNORECASE)
    return int(match.group(1)) if match else 0

def extract_quality(text):
    match = re.search(r'(4K|HD|SD|720|1080|2160)', text or '', re.IGNORECASE)
    if match:
        q = match.group(1)
        return {"720": "HD", "1080": "FHD", "2160": "4K"}.get(q, q.upper())
    return "HD"

# ===== الوظائف الأساسية =====
async def save_video_to_db(video_data):
    return db_query("""
        INSERT INTO videos (v_id, title, ep_num, video_quality, duration, poster_id, poster_caption, raw_caption, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'posted')
        ON CONFLICT (v_id) DO UPDATE SET
            title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, video_quality=EXCLUDED.video_quality,
            poster_id=COALESCE(videos.poster_id, EXCLUDED.poster_id)
    """, (
        video_data['v_id'], video_data['title'], video_data['ep_num'],
        video_data['quality'], video_data['duration'], video_data['poster_id'],
        video_data['poster_caption'], video_data['raw_caption']
    ), fetch=False) is not None

async def fetch_video_from_source(video_id):
    try:
        msg = await app.get_messages(SOURCE_CHANNEL, int(video_id))
        if not msg or msg.empty: return None
        
        media = msg.video or msg.document or msg.animation
        if not media: return None

        raw_cap = msg.caption or ""
        d = media.duration if hasattr(media, 'duration') else 0
        
        video_data = {
            'v_id': str(video_id),
            'title': clean_title(raw_cap),
            'ep_num': extract_ep_num(raw_cap),
            'quality': extract_quality(raw_cap),
            'duration': f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}",
            'poster_id': None,
            'poster_caption': None,
            'raw_caption': raw_cap
        }

        # جلب البوستر (الرسائل التالية)
        for i in range(1, 4):
            try:
                nxt = await app.get_messages(SOURCE_CHANNEL, int(video_id) + i)
                if nxt and nxt.photo:
                    video_data['poster_id'] = nxt.photo.file_id
                    video_data['poster_caption'] = nxt.caption or ""
                    if nxt.caption:
                        video_data['title'] = clean_title(nxt.caption)
                    break
            except: continue
        
        return video_data
    except: return None

# ===== أوامر البوت =====
@app.on_message(filters.command("scan") & filters.private)
async def scan_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    status_msg = await message.reply_text("🔍 جاري جلب تاريخ القناة وأرشفة الفيديوهات...")
    stats = {'videos': 0, 'posters': 0}
    
    try:
        async for msg in client.get_chat_history(SOURCE_CHANNEL, limit=500):
            if msg.video or msg.document or msg.animation:
                video_data = await fetch_video_from_source(msg.id)
                if video_data and await save_video_to_db(video_data):
                    stats['videos'] += 1
                await asyncio.sleep(0.5)
            elif msg.photo:
                stats['posters'] += 1
            
            if (stats['videos'] + stats['posters']) % 10 == 0:
                await status_msg.edit_text(f"⏳ تمت معالجة {stats['videos']} فيديو...")

        await status_msg.edit_text(f"✅ اكتمل المسح!\n📹 فيديوهات: {stats['videos']}\n🖼️ بوسترات: {stats['posters']}")
    except Exception as e:
        await status_msg.edit_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        # استخدام التابع المصحح للإرسال
        await send_video_to_user(client, message.chat.id, message.from_user.id, v_id)
    else:
        await message.reply_text("أهلاً بك! أرسل رابط الحلقة للمشاهدة.")

async def send_video_to_user(client, chat_id, user_id, video_id):
    # جلب البيانات بالأسماء الجديدة للأعمدة
    res = db_query("SELECT title, ep_num, video_quality, duration FROM videos WHERE v_id = %s", (str(video_id),))
    
    if not res:
        data = await fetch_video_from_source(video_id)
        if data: 
            await save_video_to_db(data)
            res = [(data['title'], data['ep_num'], data['quality'], data['duration'])]
        else:
            return await client.send_message(chat_id, "❌ الحلقة غير متوفرة.")

    title, ep, q, dur = res[0]
    cap = f"<b>📺 {title}</b>\n<b>🎞️ الحلقة: {ep}</b>\n<b>💿 الجودة: {q}</b>\n<b>⏳ المدة: {dur}</b>"
    
    try:
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(video_id), caption=cap, parse_mode=ParseMode.HTML)
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (str(video_id),), fetch=False)
    except Exception as e:
        await client.send_message(chat_id, f"❌ خطأ في الإرسال: {e}")

# [أوامر stats, cleardb كما هي في كودك السابق]

if __name__ == "__main__":
    init_database()
    app.run()
