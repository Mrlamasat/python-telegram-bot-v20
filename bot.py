import os
import psycopg2
import logging
import re
import asyncio
from urllib.parse import quote
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

# ===== إعداد السجلات =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== سحب الإعدادات من الاستضافة (Variables) =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# المعرفات الثابتة
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003790915936
FORCE_SUB_LINK = "https://t.me/+KyrbVyp0QCJhZGU8"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# كاش مؤقت
EPISODES_CACHE = {}
CACHE_EXPIRY = 3600  # ساعة واحدة
CACHE_TIMES = {}

# ===== قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    if not DATABASE_URL: 
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== استخراج رقم الحلقة =====
def extract_ep(text):
    if not text: return 1
    # البحث عن رقم الحلقة في النص
    match = re.search(r'(?:الحلقة|حلقة|#|EP|episode)\s*(\d+)', text, re.IGNORECASE)
    if match: 
        return int(match.group(1))
    # إذا لم يجد، يبحث عن أي رقم
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 1

def clean_title(text):
    """تنظيف العنوان من أرقام الحلقات"""
    if not text: return "مسلسل"
    # إزالة أرقام الحلقات والكلمات المرتبطة بها
    text = re.sub(r'(?:الحلقة|حلقة|#|EP|episode)\s*\d+', '', text, flags=re.IGNORECASE)
    # إزالة الروابط
    text = re.sub(r'https?://\S+', '', text)
    # تنظيف المسافات
    text = re.sub(r'\s+', ' ', text).strip()
    return text if text else "مسلسل"

# ===== محرك البحث الحي (يربط الحلقات ببعضها عبر البوستر) =====
async def fetch_live_episodes(v_id):
    v_id = int(v_id)
    
    # التحقق من الكاش
    if v_id in EPISODES_CACHE:
        cache_time = CACHE_TIMES.get(v_id, 0)
        if asyncio.get_event_loop().time() - cache_time < CACHE_EXPIRY:
            return EPISODES_CACHE[v_id]
    
    try:
        logging.info(f"🔍 بدء البحث عن حلقات قريبة من {v_id}")
        
        # البحث عن البوستر الخاص بالمسلسل
        poster_unique_id = None
        poster_caption = ""
        
        # البحث عن البوستر (أول 10 رسائل قبل الفيديو)
        for i in range(1, 11):
            try:
                m = await app.get_messages(SOURCE_CHANNEL, v_id - i)
                if m and m.photo:
                    poster_unique_id = m.photo.file_unique_id
                    poster_caption = m.caption or ""
                    logging.info(f"✅ تم العثور على بوستر: {poster_unique_id[:10]}...")
                    break
            except:
                continue
        
        if not poster_unique_id:
            logging.warning("⚠️ لم يتم العثور على بوستر")
            return []
        
        # تنظيف عنوان المسلسل من البوستر
        series_title = clean_title(poster_caption)
        logging.info(f"📺 عنوان المسلسل: {series_title}")
        
        # البحث في نطاق أوسع (300 رسالة في كل اتجاه)
        found = []
        search_range = 300
        start_id = max(1, v_id - search_range)
        end_id = v_id + search_range
        
        # نقسم البحث إلى مجموعات لتجنب الـ Flood
        for batch_start in range(start_id, end_id, 100):
            batch_ids = list(range(batch_start, min(batch_start + 100, end_id)))
            try:
                messages = await app.get_messages(SOURCE_CHANNEL, batch_ids)
                
                current_poster = None
                for msg in messages:
                    if not msg or msg.empty:
                        continue
                    
                    # تتبع آخر بوستر ظهر
                    if msg.photo:
                        current_poster = msg.photo.file_unique_id
                    
                    # إذا كان الفيديو أو الملف
                    elif msg.video or msg.document or msg.animation:
                        # التحقق من أنه يتبع نفس البوستر
                        if current_poster == poster_unique_id:
                            ep_no = extract_ep(msg.caption or "")
                            # نضيف الحلقة إذا كان لها رقم
                            if ep_no > 0:
                                found.append((msg.id, ep_no))
                                logging.info(f"✅ حلقة {ep_no} (ID: {msg.id})")
                
                # انتظار قصير بين المجموعات
                await asyncio.sleep(0.5)
                
            except FloodWait as e:
                logging.warning(f"⚠️ FloodWait: {e.value} ثانية")
                await asyncio.sleep(e.value)
            except Exception as e:
                logging.error(f"خطأ في البحث: {e}")
                continue
        
        # ترتيب النتائج حسب رقم الحلقة وإزالة التكرار
        found = list(set(found))  # إزالة التكرار
        found.sort(key=lambda x: x[1])  # ترتيب حسب رقم الحلقة
        
        logging.info(f"📊 تم العثور على {len(found)} حلقة")
        
        # حفظ في الكاش
        EPISODES_CACHE[v_id] = found
        CACHE_TIMES[v_id] = asyncio.get_event_loop().time()
        
        return found
        
    except Exception as e:
        logging.error(f"❌ خطأ في fetch_live_episodes: {e}")
        return []

async def get_episodes_markup(v_id, title, current_ep):
    episodes = await fetch_live_episodes(v_id)
    buttons, row = [], []
    bot = await app.get_me()
    
    if episodes and len(episodes) > 1:  # إذا وجد أكثر من حلقة
        for m_id, ep_no in episodes:
            # علامة صح على الحلقة الحالية
            label = f"✅ {ep_no}" if int(m_id) == int(v_id) else f"{ep_no}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot.username}?start={m_id}"))
            
            # 5 أزرار في كل صف
            if len(row) == 5:
                buttons.append(row)
                row = []
        
        # إضافة الصف الأخير إذا كان فيه أزرار
        if row:
            buttons.append(row)
        
        # إضافة أرقام الصفحات إذا كان عدد الحلقات كبيراً
        if len(episodes) > 10:
            total_pages = (len(episodes) + 9) // 10
            current_page = 1
            page_buttons = []
            for i in range(total_pages):
                page_buttons.append(InlineKeyboardButton(
                    f"📄 {i+1}" if i+1 != current_page else f"📍 {i+1}",
                    callback_data=f"page_{i}_{v_id}"
                ))
            buttons.append(page_buttons)
    
    # زر المشاركة
    share_url = f"https://t.me/{bot.username}?start={v_id}"
    tg_share = f"https://t.me/share/url?url={quote(share_url)}&text={quote(f'🎬 {title} - حلقة {current_ep}')}"
    buttons.append([InlineKeyboardButton("📢 مشاركة الحلقة", url=tg_share)])
    
    return InlineKeyboardMarkup(buttons) if buttons else None

# ===== معالج الأزرار =====
@app.on_callback_query()
async def handle_callback(client, query):
    data = query.data
    
    if data.startswith("page_"):
        # التعامل مع تغيير الصفحات
        parts = data.split("_")
        page = int(parts[1])
        v_id = int(parts[2])
        
        await query.answer(f"الصفحة {page + 1}")
        # هنا يمكن إضافة منطق تغيير الصفحة

# ===== Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(
            f"أهلاً بك يا <b>{message.from_user.first_name}</b> في بوت الحلقات.\n\n"
            "🔍 أرسل رابط الحلقة للمشاهدة"
        )
    
    v_id = message.command[1]
    
    # التحقق من الاشتراك
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        if member.status in ["left", "kicked"]:
            return await message.reply_text(
                "⚠️ <b>يجب الاشتراك في القناة أولاً</b>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📢 اشترك هنا", url=FORCE_SUB_LINK)
                ]])
            )
    except:
        # إذا كان البوت ليس في القناة أو خطأ آخر
        pass

    try:
        # جلب رسالة الحلقة
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not msg or msg.empty:
            return await message.reply_text("❌ الحلقة غير متوفرة")

        # استخراج العنوان ورقم الحلقة
        raw_cap = msg.caption or "مسلسل"
        title = clean_title(raw_cap)
        ep_no = extract_ep(raw_cap)
        
        # الحصول على أزرار الحلقات
        markup = await get_episodes_markup(v_id, title, ep_no)
        
        # تنسيق العنوان (حرف وحرف)
        styled_title = " . ".join(list(title[:30]))  # نأخذ أول 30 حرف فقط
        
        # تنسيق الكابشن
        cap = f"📺 <b>{styled_title}</b>\n"
        cap += f"🎞️ <b>الحلقة: {ep_no}</b>\n\n"
        cap += "🍿 <i>مشاهدة ممتعة!</i>"
        
        # نسخ الرسالة
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=cap,
            reply_markup=markup
        )
        
        # تحديث عدد المشاهدات
        db_query(
            "INSERT INTO videos (v_id, views) VALUES (%s, 1) ON CONFLICT (v_id) DO UPDATE SET views = videos.views + 1", 
            (v_id,), 
            fetch=False
        )

    except Exception as e:
        logging.error(f"❌ خطأ: {e}")
        await message.reply_text("❌ حدث خطأ، جرب مجدداً")

if __name__ == "__main__":
    # إنشاء جدول المشاهدات
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, 
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    
    logging.info("🚀 البوت يعمل...")
    app.run()
