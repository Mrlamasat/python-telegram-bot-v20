# file: scan_channel.py
import os
import psycopg2
import logging
import re
import asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
SOURCE_CHANNEL = -1003547072209  # قناة المصدر

app = Client("scan_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
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
        conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== دوال مساعدة =====
def clean_series_title(text):
    if not text: return "مسلسل"
    # إزالة أرقام الحلقات والروابط
    text = re.sub(r'(الحلقة|حلقة|#)?\s*\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep_num(text):
    if not text: return 0
    match = re.search(r'(?:الحلقة|حلقة|#)\s*(\d+)', text, re.IGNORECASE)
    return int(match.group(1)) if match else 0

def get_duration_str(media):
    """استخراج المدة من الفيديو"""
    if media and hasattr(media, 'duration'):
        d = media.duration
        return f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    return "00:00:00"

def extract_quality(text):
    """استخراج الجودة من النص"""
    if not text: return "HD"
    match = re.search(r'(4K|HD|SD|720|1080|2160)', text, re.IGNORECASE)
    if match:
        q = match.group(1)
        if q == "720": return "HD"
        if q == "1080": return "FHD"
        if q == "2160": return "4K"
        return q.upper()
    return "HD"

# ===== المسح الرئيسي =====
async def scan_channel():
    try:
        logging.info("🔍 بدء مسح قناة المصدر...")
        
        # إحصائيات
        total_videos = 0
        total_posters = 0
        processed = 0
        
        # قاموس لتخزين البوسترات المؤقتة
        poster_cache = {}  # poster_id -> (title, file_id)
        current_poster = None
        
        # مسح جميع الرسائل (من الأحدث إلى الأقدم)
        async for message in app.get_chat_history(SOURCE_CHANNEL, limit=5000):
            try:
                # تأخير بسيط لتجنب الـ Flood
                await asyncio.sleep(0.1)
                
                # إذا كانت الصورة (بوستر)
                if message.photo:
                    total_posters += 1
                    caption = message.caption or ""
                    title = clean_series_title(caption)
                    
                    # تخزين البوستر في الكاش
                    poster_cache[message.id] = {
                        'title': title,
                        'file_id': message.photo.file_id,
                        'caption': caption
                    }
                    
                    # تحديث البوستر الحالي
                    current_poster = message.id
                    
                    logging.info(f"🖼️ بوستر {total_posters}: {title[:30]}... (ID: {message.id})")
                
                # إذا كان فيديو أو ملف
                elif message.video or message.document or message.animation:
                    total_videos += 1
                    
                    # البحث عن آخر بوستر قبل هذا الفيديو
                    poster_id = None
                    poster_title = "مسلسل"
                    poster_caption = ""
                    
                    # البحث في الكاش أولاً
                    for pid in sorted(poster_cache.keys(), reverse=True):
                        if pid < message.id:
                            poster_id = pid
                            poster_title = poster_cache[pid]['title']
                            poster_caption = poster_cache[pid]['caption']
                            break
                    
                    # إذا لم نجد في الكاش، نبحث في الرسائل
                    if not poster_id:
                        for i in range(1, 11):
                            try:
                                prev_msg = await app.get_messages(SOURCE_CHANNEL, message.id - i)
                                if prev_msg and prev_msg.photo:
                                    poster_id = prev_msg.id
                                    poster_title = clean_series_title(prev_msg.caption or "")
                                    poster_caption = prev_msg.caption or ""
                                    
                                    # إضافة للكاش
                                    poster_cache[poster_id] = {
                                        'title': poster_title,
                                        'file_id': prev_msg.photo.file_id,
                                        'caption': poster_caption
                                    }
                                    break
                            except:
                                continue
                    
                    # استخراج البيانات
                    media = message.video or message.animation
                    duration = get_duration_str(media)
                    ep_num = extract_ep_num(message.caption or "")
                    
                    # استخراج الجودة
                    quality = extract_quality(message.caption or "")
                    
                    # حفظ في قاعدة البيانات
                    db_query("""
                        INSERT INTO videos (
                            v_id, title, ep_num, quality, duration, 
                            poster_id, poster_caption, status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'posted')
                        ON CONFLICT (v_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            ep_num = EXCLUDED.ep_num,
                            quality = EXCLUDED.quality,
                            poster_id = EXCLUDED.poster_id,
                            poster_caption = EXCLUDED.poster_caption,
                            status = 'posted'
                    """, (
                        str(message.id), 
                        poster_title, 
                        ep_num, 
                        quality, 
                        duration,
                        poster_cache.get(poster_id, {}).get('file_id', '') if poster_id else '',
                        poster_caption[:200],  # نأخذ أول 200 حرف فقط
                    ), fetch=False)
                    
                    processed += 1
                    
                    if processed % 50 == 0:
                        logging.info(f"📊 تمت معالجة {processed} فيديو...")
                    
                    logging.info(f"🎬 فيديو {processed}: {poster_title[:20]} - حلقة {ep_num} (ID: {message.id})")
            
            except FloodWait as e:
                logging.warning(f"⚠️ FloodWait: {e.value} ثانية")
                await asyncio.sleep(e.value)
            
            except Exception as e:
                logging.error(f"❌ خطأ في معالجة رسالة {message.id}: {e}")
                continue
        
        logging.info(f"✅ اكتمل المسح!")
        logging.info(f"📊 إحصائيات:")
        logging.info(f"   - إجمالي البوسترات: {total_posters}")
        logging.info(f"   - إجمالي الفيديوهات: {total_videos}")
        logging.info(f"   - تمت المعالجة: {processed}")
        
        # إحصائيات حسب المسلسل
        series_stats = db_query("""
            SELECT title, COUNT(*) as episodes, SUM(views) as total_views
            FROM videos 
            GROUP BY title 
            ORDER BY episodes DESC
        """)
        
        if series_stats:
            logging.info("📊 المسلسلات في القناة:")
            for title, eps, views in series_stats[:10]:  # أول 10 مسلسلات
                logging.info(f"   - {title[:30]}: {eps} حلقة | {views or 0} مشاهدة")
        
        return processed
        
    except Exception as e:
        logging.error(f"❌ خطأ كبير في المسح: {e}")
        return 0

# ===== تشغيل المسح =====
async def main():
    async with app:
        count = await scan_channel()
        print(f"\n✅ تمت معالجة {count} فيديو بنجاح!")

if __name__ == "__main__":
    # إنشاء جدول videos إذا لم يكن موجوداً
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER,
            quality TEXT DEFAULT 'HD',
            duration TEXT,
            poster_id TEXT,
            poster_caption TEXT,
            status TEXT DEFAULT 'posted',
            views INTEGER DEFAULT 0,
            scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    print("🚀 بدء مسح قناة المصدر...")
    asyncio.run(main())
