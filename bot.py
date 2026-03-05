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

# ===== قاعدة البيانات =====
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
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    # التأكد من وجود الأعمدة في حال تم تحديث الجدول
    try:
        db_query("ALTER TABLE videos ADD COLUMN IF NOT EXISTS video_quality TEXT DEFAULT 'HD'", fetch=False)
    except: pass

# ===== دوال الاستخراج الذكية =====
def extract_ep_num(text):
    if not text: return 0
    # البحث عن "الحلقة X" أو "حلقة X" أو "#X"
    match = re.search(r'(?:الحلقة|حلقة|#|EP|Episode)\s*(\d+)', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # محاولة جلب أي رقم من النص إذا فشل البحث السابق
    numbers = re.findall(r'\d+', text)
    return int(numbers[-1]) if numbers else 0

def clean_title(text):
    if not text: return "مسلسل"
    # إزالة رقم الحلقة والروابط والرموز
    text = re.sub(r'(?:الحلقة|حلقة|#|EP|Episode)\s*\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', text) # الاحتفاظ بالعربي والانجليزي فقط
    return text.strip() or "مسلسل"

def extract_quality(text):
    match = re.search(r'(4K|HD|SD|720|1080|2160)', text or '', re.IGNORECASE)
    if match:
        q = match.group(1)
        return {"720": "HD", "1080": "FHD", "2160": "4K"}.get(q, q.upper())
    return "HD"

# ===== جلب بيانات الفيديو وحفظها =====
async def archive_video(video_msg):
    try:
        v_id = str(video_msg.id)
        raw_cap = video_msg.caption or ""
        
        # استخراج البيانات الأولية من الفيديو
        ep = extract_ep_num(raw_cap)
        title = clean_title(raw_cap)
        quality = extract_quality(raw_cap)
        
        media = video_msg.video or video_msg.document or video_msg.animation
        d = media.duration if hasattr(media, 'duration') and media.duration else 0
        duration = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"

        # البحث عن البوستر (الصورة التي تلي الفيديو مباشرة)
        poster_id = None
        poster_cap = ""
        
        for i in range(1, 4): # البحث في الـ 3 رسائل التالية
            try:
                next_msg = await app.get_messages(SOURCE_CHANNEL, video_msg.id + i)
                if next_msg and next_msg.photo:
                    poster_id = next_msg.photo.file_id
                    poster_cap = next_msg.caption or ""
                    # إذا كان رقم الحلقة غير موجود في الفيديو، نأخذه من البوستر
                    if ep == 0: ep = extract_ep_num(poster_cap)
                    # إذا كان العنوان "مسلسل"، نأخذ العنوان من البوستر
                    if title == "مسلسل": title = clean_title(poster_cap)
                    break
            except: continue

        # حفظ في قاعدة البيانات
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, video_quality, duration, poster_id, poster_caption, raw_caption)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (v_id) DO UPDATE SET 
            title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, video_quality=EXCLUDED.video_quality,
            poster_id=COALESCE(videos.poster_id, EXCLUDED.poster_id)
        """, (v_id, title, ep, quality, duration, poster_id, poster_cap, raw_cap), fetch=False)
        return True
    except Exception as e:
        logging.error(f"Error archiving {video_msg.id}: {e}")
        return False

# ===== الأوامر =====
@app.on_message(filters.command("scan") & filters.private)
async def scan_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    m = await message.reply_text("🔍 جاري فحص القناة وأرشفة الحلقات (فيديو ← صورة)...")
    count = 0
    
    try:
        async for msg in client.get_chat_history(SOURCE_CHANNEL, limit=1000):
            if msg.video or msg.document or msg.animation:
                if await archive_video(msg):
                    count += 1
                await asyncio.sleep(0.5) # تجنب الحظر
                
            if count % 10 == 0 and count > 0:
                await m.edit_text(f"⏳ تم أرشفة {count} حلقة حتى الآن...")

        await m.edit_text(f"✅ اكتملت الأرشفة بنجاح!\n📹 إجمالي الحلقات: {count}")
    except Exception as e:
        await m.edit_text(f"❌ خطأ أثناء المسح: {e}")

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num, video_quality, duration FROM videos WHERE v_id = %s", (str(v_id),))
        
        if res:
            title, ep, q, dur = res[0]
            # تنسيق العنوان لمنع الحظر (اضافة نقاط)
            safe_title = " . ".join(list(title[:50]))
            cap = (
                f"<b>📺 المسلسل: {safe_title}</b>\n"
                f"<b>🎞️ الحلقة: {ep}</b>\n"
                f"<b>💿 الجودة: {q}</b>\n"
                f"<b>⏳ المدة: {dur}</b>\n\n"
                f"🍿 مشاهدة ممتعة!"
            )
            
            # جلب أزرار الحلقات المرتبطة بنفس العنوان
            eps = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s ORDER BY ep_num ASC", (title,))
            buttons = []
            if eps and len(eps) > 1:
                row = []
                for vid, enp in eps:
                    label = f"📍 {enp}" if str(vid) == str(v_id) else f"{enp}"
                    row.append(InlineKeyboardButton(label, url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
                    if len(row) == 5:
                        buttons.append(row)
                        row = []
                if row: buttons.append(row)

            await client.copy_message(
                message.chat.id, 
                SOURCE_CHANNEL, 
                int(v_id), 
                caption=cap, 
                reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
            )
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (str(v_id),), fetch=False)
        else:
            await message.reply_text("❌ عذراً، لم يتم العثور على بيانات هذه الحلقة.")
    else:
        await message.reply_text(f"أهلاً {message.from_user.first_name}، أرسل رابط الحلقة للمشاهدة.")

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    views = db_query("SELECT SUM(views) FROM videos")[0][0] or 0
    await message.reply_text(f"📊 إحصائيات البوت:\n\n📹 الحلقات المؤرشفة: {total}\n👤 إجمالي المشاهدات: {views}")

if __name__ == "__main__":
    init_database()
    logging.info("🚀 البوت بدأ العمل...")
    app.run()
