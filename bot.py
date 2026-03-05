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

# ===== معرفات القنوات =====
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003790915936
FORCE_SUB_LINK = "https://t.me/+nLtMePUz6lw3YzBk"
PUBLIC_POST_CHANNEL = -1003678294148

# ===== تأخير ذكي لتجنب الحظر =====
def smart_delay():
    last_run_file = "last_run.txt"
    try:
        if os.path.exists(last_run_file):
            with open(last_run_file, 'r') as f:
                last_run = float(f.read().strip())
                if (time.time() - last_run) < 60:
                    delay = random.randint(30, 60)
                    print(f"⏳ انتظار {delay} ثانية للأمان...")
                    time.sleep(delay)
    except: pass
    with open(last_run_file, 'w') as f:
        f.write(str(time.time()))

smart_delay()

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

# ===== إنشاء الجدول بشكل صحيح =====
def init_database():
    """إنشاء جدول البيانات مع جميع الأعمدة المطلوبة"""
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            video_quality TEXT DEFAULT 'HD',
            duration TEXT DEFAULT '00:00:00',
            poster_id TEXT,
            poster_caption TEXT,
            poster_message_id BIGINT,
            raw_caption TEXT,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    logging.info("✅ تم التأكد من وجود جدول البيانات")

# ===== دوال الاستخراج من النصوص =====
def clean_title(text):
    """استخراج عنوان المسلسل من النص"""
    if not text: return "مسلسل"
    # إزالة رقم الحلقة والروابط
    text = re.sub(r'(?:الحلقة|حلقة|#)\s*\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep_num(text):
    """استخراج رقم الحلقة"""
    if not text: return 0
    match = re.search(r'(?:الحلقة|حلقة|#)\s*(\d+)', text, re.IGNORECASE)
    return int(match.group(1)) if match else 0

def extract_quality(text):
    """استخراج الجودة"""
    if not text: return "HD"
    match = re.search(r'(4K|HD|SD|720|1080|2160)', text, re.IGNORECASE)
    if match:
        q = match.group(1)
        return {"720": "HD", "1080": "FHD", "2160": "4K"}.get(q, q.upper())
    return "HD"

def get_duration(media):
    """استخراج المدة من وسائط الفيديو"""
    if media and hasattr(media, 'duration'):
        d = media.duration
        return f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    return "00:00:00"

# ===== جلب بيانات الفيديو من المصدر (مع البحث عن البوستر بعد الفيديو) =====
async def fetch_video_from_source(video_id):
    """جلب بيانات الفيديو من القناة مع البحث عن البوستر الذي يليه"""
    try:
        msg = await app.get_messages(SOURCE_CHANNEL, int(video_id))
        if not msg or msg.empty:
            return None
        
        # استخراج البيانات الأساسية من الفيديو
        raw_caption = msg.caption or ""
        title_from_video = clean_title(raw_caption)
        ep_num = extract_ep_num(raw_caption)
        quality = extract_quality(raw_caption)
        
        # استخراج المدة
        media = msg.video or msg.animation or msg.document
        duration = get_duration(media)
        
        # البحث عن البوستر بعد الفيديو
        poster_id = None
        poster_caption = ""
        poster_message_id = None
        
        # البحث في الـ 5 رسائل التالية
        for i in range(1, 6):
            try:
                next_msg = await app.get_messages(SOURCE_CHANNEL, int(video_id) + i)
                if next_msg and next_msg.photo:
                    poster_id = next_msg.photo.file_id
                    poster_caption = next_msg.caption or ""
                    poster_message_id = next_msg.id
                    
                    # عنوان المسلسل الحقيقي موجود في البوستر
                    if poster_caption:
                        title_from_poster = clean_title(poster_caption)
                        if title_from_poster and title_from_poster != "مسلسل":
                            title_from_video = title_from_poster
                    break
                await asyncio.sleep(0.1)
            except:
                continue
        
        return {
            'v_id': str(video_id),
            'title': title_from_video,
            'ep_num': ep_num,
            'quality': quality,
            'duration': duration,
            'poster_id': poster_id,
            'poster_caption': poster_caption,
            'poster_message_id': poster_message_id,
            'raw_caption': raw_caption
        }
        
    except FloodWait as e:
        logging.warning(f"⚠️ FloodWait في fetch_video: {e.value}")
        await asyncio.sleep(e.value)
        return await fetch_video_from_source(video_id)
    except Exception as e:
        logging.error(f"❌ خطأ في fetch_video: {e}")
        return None

# ===== حفظ الفيديو في قاعدة البيانات =====
async def save_video_to_db(video_data):
    """حفظ بيانات الفيديو في قاعدة البيانات"""
    if not video_data:
        return False
    
    try:
        db_query("""
            INSERT INTO videos (
                v_id, title, ep_num, video_quality, duration, 
                poster_id, poster_caption, poster_message_id, raw_caption, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET
                title = EXCLUDED.title,
                ep_num = EXCLUDED.ep_num,
                video_quality = EXCLUDED.video_quality,
                duration = EXCLUDED.duration,
                poster_id = EXCLUDED.poster_id,
                poster_caption = EXCLUDED.poster_caption,
                poster_message_id = EXCLUDED.poster_message_id,
                raw_caption = EXCLUDED.raw_caption,
                status = 'posted'
        """, (
            video_data['v_id'],
            video_data['title'],
            video_data['ep_num'],
            video_data['quality'],
            video_data['duration'],
            video_data['poster_id'],
            video_data['poster_caption'],
            video_data.get('poster_message_id'),
            video_data['raw_caption']
        ), fetch=False)
        return True
    except Exception as e:
        logging.error(f"❌ خطأ في حفظ البيانات: {e}")
        return False

# ===== مسح القناة باستخدام iter_messages (بديل get_chat_history) =====
async def scan_channel_full(client, limit=500):
    """مسح القناة باستخدام iter_messages (طريقة آمنة للبوتات)"""
    stats = {'videos': 0, 'posters': 0, 'errors': 0}
    
    try:
        # استخدام iter_messages بدلاً من get_chat_history
        async for message in client.iter_messages(SOURCE_CHANNEL, limit=limit):
            try:
                # إذا كان فيديو
                if message.video or message.document or message.animation:
                    # استخراج البيانات من الفيديو
                    raw_caption = message.caption or ""
                    title = clean_title(raw_caption)
                    ep_num = extract_ep_num(raw_caption)
                    quality = extract_quality(raw_caption)
                    duration = get_duration(message.video or message.animation)
                    
                    # بيانات الفيديو
                    video_data = {
                        'v_id': str(message.id),
                        'title': title,
                        'ep_num': ep_num,
                        'quality': quality,
                        'duration': duration,
                        'poster_id': None,
                        'poster_caption': None,
                        'poster_message_id': None,
                        'raw_caption': raw_caption
                    }
                    
                    # البحث عن البوستر بعد هذا الفيديو
                    for i in range(1, 6):
                        try:
                            next_id = message.id + i
                            next_msg = await client.get_messages(SOURCE_CHANNEL, next_id)
                            if next_msg and next_msg.photo:
                                video_data['poster_id'] = next_msg.photo.file_id
                                video_data['poster_caption'] = next_msg.caption or ""
                                video_data['poster_message_id'] = next_id
                                
                                # تحديث العنوان من البوستر
                                if next_msg.caption:
                                    poster_title = clean_title(next_msg.caption)
                                    if poster_title and poster_title != "مسلسل":
                                        video_data['title'] = poster_title
                                break
                            await asyncio.sleep(0.2)
                        except:
                            continue
                    
                    # حفظ الفيديو
                    if await save_video_to_db(video_data):
                        stats['videos'] += 1
                    
                    await asyncio.sleep(0.5)
                
                # إذا كان بوستر
                elif message.photo:
                    stats['posters'] += 1
                
            except FloodWait as e:
                wait_time = e.value
                logging.warning(f"⚠️ FloodWait: {wait_time}")
                await asyncio.sleep(wait_time)
            except Exception as e:
                stats['errors'] += 1
                logging.error(f"❌ خطأ في معالجة رسالة {message.id}: {e}")
                continue
        
        return stats
        
    except Exception as e:
        logging.error(f"❌ خطأ في المسح: {e}")
        return stats

# ===== جلب جميع الحلقات المرتبطة بنفس البوستر =====
async def get_series_episodes(video_id):
    """جلب جميع حلقات نفس المسلسل باستخدام البوستر"""
    video_info = db_query("""
        SELECT title, poster_id FROM videos WHERE v_id = %s
    """, (str(video_id),))
    
    if not video_info:
        return []
    
    title, poster_id = video_info[0]
    
    if poster_id:
        episodes = db_query("""
            SELECT v_id, ep_num FROM videos 
            WHERE poster_id = %s AND status = 'posted'
            ORDER BY ep_num ASC
        """, (poster_id,))
    else:
        episodes = db_query("""
            SELECT v_id, ep_num FROM videos 
            WHERE title = %s AND status = 'posted'
            ORDER BY ep_num ASC
        """, (title,))
    
    return episodes or []

# ===== إنشاء أزرار الحلقات =====
async def create_episodes_buttons(video_id, current_v_id):
    """إنشاء أزرار الحلقات المرتبطة"""
    episodes = await get_series_episodes(video_id)
    
    if not episodes or len(episodes) <= 1:
        return None
    
    buttons, row = [], []
    bot = await app.get_me()
    
    for vid, ep in episodes:
        label = f"📍 {ep}" if str(vid) == str(current_v_id) else f"{ep}"
        row.append(InlineKeyboardButton(
            label, 
            url=f"https://t.me/{bot.username}?start={vid}"
        ))
        
        if len(row) == 5:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    return InlineKeyboardMarkup(buttons)

# ===== إرسال الفيديو للمستخدم =====
async def send_video_to_user(client, chat_id, user_id, video_id):
    """إرسال الفيديو مع جميع البيانات"""
    
    video_in_db = db_query("SELECT * FROM videos WHERE v_id = %s", (str(video_id),))
    
    if not video_in_db:
        video_data = await fetch_video_from_source(video_id)
        if not video_data:
            return await client.send_message(chat_id, "❌ الفيديو غير موجود في المصدر")
        await save_video_to_db(video_data)
    
    video_info = db_query("""
        SELECT title, ep_num, video_quality, duration, poster_id 
        FROM videos WHERE v_id = %s
    """, (str(video_id),))
    
    if not video_info:
        return await client.send_message(chat_id, "❌ خطأ في جلب البيانات")
    
    title, ep_num, quality, duration, poster_id = video_info[0]
    
    db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (str(video_id),), fetch=False)
    
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        subscribed = member.status not in ["left", "kicked"]
    except:
        subscribed = False
    
    episodes_buttons = await create_episodes_buttons(video_id, video_id)
    
    safe_title = " . ".join(list(title[:50]))
    caption = (
        f"<b>📺 المسلسل: {safe_title}</b>\n"
        f"<b>🎞️ الحلقة: {ep_num}</b>\n"
        f"<b>💿 الجودة: {quality}</b>\n"
        f"<b>⏳ المدة: {duration}</b>\n\n"
        f"🍿 مشاهدة ممتعة!"
    )
    
    if not subscribed:
        sub_button = [InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)]
        
        if episodes_buttons:
            markup = InlineKeyboardMarkup([sub_button] + episodes_buttons.inline_keyboard)
        else:
            markup = InlineKeyboardMarkup([sub_button])
        
        return await client.send_message(
            chat_id,
            "⚠️ يجب الاشتراك في القناة للمشاهدة",
            reply_markup=markup
        )
    
    try:
        await client.copy_message(
            chat_id,
            SOURCE_CHANNEL,
            int(video_id),
            caption=caption,
            reply_markup=episodes_buttons,
            parse_mode=ParseMode.HTML
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await send_video_to_user(client, chat_id, user_id, video_id)
    except Exception as e:
        logging.error(f"❌ خطأ في الإرسال: {e}")
        await client.send_message(chat_id, "❌ حدث خطأ في الإرسال")

# ===== أوامر البوت =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if len(message.command) > 1:
        video_id = message.command[1]
        await send_video_to_user(client, message.chat.id, message.from_user.id, video_id)
    else:
        welcome = (
            f"أهلاً <b>{escape(message.from_user.first_name)}</b>!\n\n"
            "🔗 أرسل رابط الحلقة للمشاهدة"
        )
        await message.reply_text(welcome, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("scan") & filters.private)
async def scan_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    msg = await message.reply_text("🔍 جاري مسح القناة...")
    
    try:
        stats = await scan_channel_full(client, limit=500)
        
        result = (
            f"✅ <b>تم المسح بنجاح!</b>\n\n"
            f"📹 فيديوهات: {stats['videos']}\n"
            f"🖼️ بوسترات: {stats['posters']}\n"
            f"❌ أخطاء: {stats['errors']}"
        )
        await msg.edit_text(result, parse_mode=ParseMode.HTML)
        
    except FloodWait as e:
        await msg.edit_text(f"⚠️ FloodWait: انتظر {e.value} ثانية")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    total = db_query("SELECT COUNT(*) FROM videos", fetch=True)
    total_views = db_query("SELECT SUM(views) FROM videos", fetch=True)
    series_count = db_query("SELECT COUNT(DISTINCT title) FROM videos", fetch=True)
    with_poster = db_query("SELECT COUNT(*) FROM videos WHERE poster_id IS NOT NULL", fetch=True)
    
    top = db_query("""
        SELECT title, ep_num, views FROM videos 
        ORDER BY views DESC LIMIT 10
    """)
    
    text = "📊 <b>إحصائيات البوت</b>\n\n"
    text += f"📹 إجمالي الفيديوهات: {total[0][0] if total else 0}\n"
    text += f"📺 عدد المسلسلات: {series_count[0][0] if series_count else 0}\n"
    text += f"🖼️ فيديوهات ببوستر: {with_poster[0][0] if with_poster else 0}\n"
    text += f"👤 إجمالي المشاهدات: {total_views[0][0] if total_views else 0}\n\n"
    text += "🏆 <b>الأكثر مشاهدة:</b>\n\n"
    
    if top:
        for i, row in enumerate(top, 1):
            text += f"{i}. {escape(row[0][:30])} - حلقة {row[1]} 👤 {row[2]}\n"
    else:
        text += "لا توجد إحصائيات"
    
    await message.reply_text(text, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("cleardb") & filters.private)
async def cleardb_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    db_query("DELETE FROM videos", fetch=False)
    await message.reply_text("✅ تم مسح قاعدة البيانات")

@app.on_message(filters.command("restart") & filters.private)
async def restart_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.reply_text("🔄 جاري إعادة التشغيل...")
    await asyncio.sleep(2)
    os._exit(0)

# ===== تشغيل البوت =====
if __name__ == "__main__":
    # تهيئة قاعدة البيانات
    init_database()
    
    logging.info("🚀 بوت جلب الفيديوهات من المصدر يعمل...")
    
    while True:
        try:
            app.run()
            break
        except FloodWait as e:
            wait_time = e.value + random.randint(5, 15)
            logging.warning(f"⚠️ FloodWait كبير: {e.value} ثانية")
            print(f"⏳ انتظار {wait_time} ثانية...")
            time.sleep(wait_time)
        except KeyboardInterrupt:
            print("👋 تم إيقاف البوت")
            break
        except Exception as e:
            logging.error(f"❌ خطأ غير متوقع: {e}")
            time.sleep(30)
