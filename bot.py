import os
import psycopg2
import psycopg2.pool
import logging
import re
import difflib
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from pyrogram.enums import ParseMode

# إعداد السجلات (Logs)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الأساسية (تأكد من وجودها في Railway Variables) =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات (Pool) =====
db_pool = None

def get_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")
    return db_pool

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        pool = get_pool()
        conn = pool.getconn()
        conn.set_client_encoding('UTF8')
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

# ===== دوال التنظيف والاستخراج الذكي =====
def convert_ar_no(text):
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return text.translate(trans)

def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'[أإآأ]', 'ا', text); text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ى', 'ي', text); text = re.sub(r'^(ال)', '', text)
    return re.sub(r'\s+', '', text)

def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text) 
    # تنظيف أفضل للعنوان
    text = re.sub(r'الحلقة\s*\d+.*$|حلقة\s*\d+.*$|\[?\d+\]?.*$|الجودة:.*$|المدة:.*$|\[.*?\]', '', text, flags=re.IGNORECASE)
    return text.strip()

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

# ===== نظام أزرار الحلقات =====
async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return []
    
    buttons, row = [], []
    me = await app.get_me()
    
    for v_id, ep_num in res:
        # تمييز الحلقة الحالية بعلامة ✅
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={v_id}"))
        
        if len(row) == 5:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    return buttons

# ===== نظام النشر التلقائي الذكي =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def auto_post_handler(client, message):
    v_id = str(message.id)
    caption = message.caption or ""
    
    # استخراج العنوان ورقم الحلقة بشكل أفضل
    title = clean_series_title(caption)
    
    # البحث عن رقم الحلقة في الكابشن
    ep_match = re.search(r'(?:الحلقة|حلقة|#)?\s*[:\-]?\s*(\d+)', caption, re.IGNORECASE)
    real_ep = int(ep_match.group(1)) if ep_match else 1
    
    # تخزين في قاعدة البيانات
    db_query("""
        INSERT INTO videos (v_id, title, ep_num, status) 
        VALUES (%s, %s, %s, 'posted') 
        ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s
    """, (v_id, title, real_ep, title, real_ep), fetch=False)
    
    # إنشاء رسالة النشر العام
    me = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    
    # استخراج المعلومات الإضافية من الكابشن
    quality_match = re.search(r'الجودة:?\s*\[?([^\]]+)\]?', caption, re.IGNORECASE)
    duration_match = re.search(r'المدة:?\s*\[?([^\]]+)\]?', caption, re.IGNORECASE)
    
    quality = quality_match.group(1).strip() if quality_match else "HD"
    duration = duration_match.group(1).strip() if duration_match else "00:00:00"
    
    pub_text = (
        f"🎬 <b>{safe_t}</b>\n\n"
        f"📌 <b>الحلقة: [{real_ep}]</b>\n"
        f"⚡ <b>الجودة: [{quality}]</b>\n"
        f"⏱ <b>المدة: [{duration}]</b>\n\n"
        f"👇 اضغط هنا للمشاهدة فوراً"
    )
    
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ شاهد الحلقة الآن", url=f"https://t.me/{me.username}?start={v_id}")
    ]])
    
    try:
        await client.send_message(PUBLIC_POST_CHANNEL, pub_text, reply_markup=markup, parse_mode=ParseMode.HTML)
        logging.info(f"✅ تم نشر الحلقة {real_ep} من {title}")
    except Exception as e:
        logging.error(f"❌ Auto-post failed: {e}")

# ===== معالجة الـ Start وجلب الفيديوهات =====
@app.on_message(filters.command("start") & filters.private)
async def handle_start(client, message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(f"مرحباً بك يا <b>{escape(message.from_user.first_name)}</b>!", parse_mode=ParseMode.HTML)
    
    v_id = message.command[1]
    
    # فحص الاشتراك الإجباري
    if user_id != ADMIN_ID:
        try:
            user_status = await client.get_chat_member(int(FORCE_SUB_CHANNEL), user_id)
            if user_status.status in ["left", "kicked"]:
                return await message.reply_text(
                    "⚠️ **يجب الانضمام لقناتنا لمشاهدة الحلقة:**",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📥 اضغط هنا للانضمام", url=FORCE_SUB_LINK)
                    ]])
                )
        except Exception as e:
            logging.error(f"Force sub check error: {e}")
            # إذا فشل الفحص، نسمح بالمشاهدة
            pass
    
    try:
        # جلب بيانات الحلقة من قاعدة البيانات
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not res:
            # إذا لم توجد في قاعدة البيانات، نحاول جلبها من المصدر
            try:
                source_chat = await client.get_chat(int(SOURCE_CHANNEL))
                msg = await client.get_messages(source_chat.id, int(v_id))
                
                if msg and msg.caption:
                    title = clean_series_title(msg.caption)
                    ep_match = re.search(r'(?:الحلقة|حلقة|#)?\s*[:\-]?\s*(\d+)', msg.caption, re.IGNORECASE)
                    ep = int(ep_match.group(1)) if ep_match else 1
                    
                    # تخزين في قاعدة البيانات
                    db_query("""
                        INSERT INTO videos (v_id, title, ep_num, status) 
                        VALUES (%s, %s, %s, 'posted')
                    """, (v_id, title, ep), fetch=False)
                else:
                    return await message.reply_text("❌ لم نتمكن من العثور على هذه الحلقة.")
            except Exception as e:
                logging.error(f"Error fetching from source: {e}")
                return await message.reply_text("❌ حدث خطأ في جلب الحلقة.")
        else:
            title, ep = res[0]
        
        # إنشاء أزرار الحلقات
        btns = await get_episodes_markup(title, v_id)
        
        # إنشاء الكابشن
        cap = f"<b>📺 {obfuscate_visual(escape(title))}</b>\n<b>🎞️ الحلقة: {ep}</b>"
        
        # إرسال الحلقة
        source_chat = await client.get_chat(int(SOURCE_CHANNEL))
        await client.copy_message(
            message.chat.id, 
            source_chat.id, 
            int(v_id), 
            caption=cap, 
            reply_markup=InlineKeyboardMarkup(btns) if btns else None
        )
        
        logging.info(f"✅ تم إرسال الحلقة {ep} من {title} للمستخدم {user_id}")
        
    except Exception as e:
        logging.error(f"Error in start handler: {e}")
        await message.reply_text("❌ حدث خطأ أثناء جلب الحلقة. يرجى المحاولة لاحقاً.")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    # إنشاء جدول قاعدة البيانات إذا لم يكن موجوداً
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, 
            title TEXT, 
            ep_num INTEGER, 
            status TEXT DEFAULT 'posted', 
            views INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    
    logging.info("🚀 Bot is running successfully...")
    app.run()
