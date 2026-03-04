import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from pyrogram.enums import ParseMode

# ===== الإعدادات الأساسية =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

# IDs القنوات الصحيحة
SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307  # القناة المطلوبة
FORCE_SUB_CHANNEL = -1003894735143     
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إعداد قاعدة البيانات مع إنشاء الجداول =====
def init_database():
    """إنشاء الجداول إذا لم تكن موجودة"""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        
        # إنشاء جدول videos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                v_id TEXT PRIMARY KEY,
                title TEXT,
                poster_id TEXT,
                quality TEXT,
                duration TEXT,
                ep_num TEXT,
                views INTEGER DEFAULT 0,
                status TEXT DEFAULT 'waiting',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ تم إنشاء/التحقق من جداول قاعدة البيانات")
        return True
    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء قاعدة البيانات: {e}")
        return False

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
        logging.error(f"❌ DB Error: {e}")
        return None

# ===== معالجة النص والبحث الذكي =====
def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    # إزالة كلمة "مسلسل" أو "فيلم" للتركيز على الاسم
    text = re.sub(r'^(مسلسل|فيلم|برنامج|عرض)\s+', '', text)
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ة]', 'ه', text)
    text = re.sub(r'[ى]', 'ي', text)
    # إزالة النقاط والمسافات للمطابقة الدقيقة
    text = re.sub(r'[^a-z0-9ا-ي]', '', text)
    return text

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text.replace(" ", "")))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

# ===== القائمة السفلية =====
MAIN_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton("🔍 كيف أبحث عن مسلسل؟")], [KeyboardButton("✍️ طلب مسلسل جديد")]],
    resize_keyboard=True
)

# ===== 1. كود الإحصائيات =====
@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    res_total = db_query("SELECT COUNT(*), SUM(COALESCE(views, 0)) FROM videos WHERE status='posted'")
    res_top = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 5")
    
    total_eps = res_total[0][0] if res_total and res_total[0][0] else 0
    total_views = res_total[0][1] if res_total and res_total[0][1] else 0
    
    text = f"📊 **إحصائيات المنصة:**\n\n"
    text += f"📽️ إجمالي الحلقات: `{total_eps}`\n"
    text += f"👁️ إجمالي المشاهدات: `{total_views}`\n\n"
    text += "🔥 **الأكثر مشاهدة:**\n"
    
    if res_top:
        for i, r in enumerate(res_top, 1):
            text += f"{i}. {r[0]} (حلقة {r[1]}) ← {r[2]} مشاهدة\n"
    else:
        text += "لا توجد بيانات بعد"
    
    await message.reply_text(text)

# ===== 2. نظام النشر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    
    # جلب آخر فيديو ينتظر رقم الحلقة
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY created_at DESC LIMIT 1")
    if not res:
        await message.reply_text("❌ لا يوجد فيديو في انتظار رقم الحلقة")
        return
    
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    me = await client.get_me()
    caption = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n<b>الحلقة: [{ep_num}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start=choose_{v_id}")]])
    
    try:
        # النشر باستخدام ID القناة الرقمي المباشر
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
        await message.reply_text("🚀 تم النشر بنجاح في القناة العامة.")
    except Exception as e:
        await message.reply_text(f"❌ خطأ في النشر: {e}")

# ===== 3. نظام البحث =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def message_handler(client, message):
    if message.text == "🔍 كيف أبحث عن مسلسل؟":
        await message.reply_text("🔎 اكتب اسم المسلسل مباشرة (مثلاً: الكينج) وسأظهر لك النتائج.", reply_markup=MAIN_MENU)
        return
    if message.text == "✍️ طلب مسلسل جديد":
        await message.reply_text("📥 أرسل اسم المسلسل وسأبلغ الإدارة فوراً.", reply_markup=MAIN_MENU)
        return

    query = normalize_text(message.text)
    if len(query) < 2: return

    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    if not res:
        await message.reply_text("❌ لا توجد مسلسلات في قاعدة البيانات بعد.")
        return
        
    matches = [t[0] for t in res if query in normalize_text(t[0])]
    
    if matches:
        btns = [[InlineKeyboardButton(f"🎬 {m}", callback_data=f"lst_{m[:40]}")] for m in list(dict.fromkeys(matches))[:10]]
        await message.reply_text(f"🔍 نتائج البحث عن '{message.text}':", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await message.reply_text(f"❌ لم أجد '{message.text}'. تم إبلاغ الإدارة.")

# ===== استقبال الفيديو =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    db_query("INSERT INTO videos (v_id, status, duration, created_at) VALUES (%s, 'waiting', %s, CURRENT_TIMESTAMP) ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id, dur), fetch=False)
    await message.reply_text(f"✅ تم استقبال الملف. أرسل البوستر الآن.")

# ===== استقبال البوستر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY created_at DESC LIMIT 1")
    if not res:
        await message.reply_text("❌ لا يوجد فيديو في انتظار بوستر")
        return
    v_id = res[0][0]
    title = clean_series_title(message.caption or "مسلسل")
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), 
         InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), 
         InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]
    ])
    await message.reply_text(f"📌 المسلسل: {title}\nاختر الجودة:", reply_markup=markup)

# ===== اختيار الجودة =====
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن رقم الحلقة:")

# ===== أمر start =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    welcome_text = f"👋 أهلاً بك يا {message.from_user.first_name}\n\n"
    welcome_text += "مرحباً بك في بوت المسلسلات\n"
    welcome_text += "يمكنك البحث عن أي مسلسل بكتابة اسمه"
    
    await message.reply_text(welcome_text, reply_markup=MAIN_MENU)

# ===== تشغيل البوت مع تهيئة قاعدة البيانات =====
if __name__ == "__main__":
    # تهيئة قاعدة البيانات أولاً
    if init_database():
        print("✅ تم تهيئة قاعدة البيانات بنجاح")
        print("🚀 تشغيل البوت...")
        app.run()
    else:
        print("❌ فشل في تهيئة قاعدة البيانات. تأكد من اتصال DATABASE_URL")
