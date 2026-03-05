import os
import psycopg2
import psycopg2.pool
import logging
import re
import asyncio
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الأساسية (تأكد من صحتها في بيئة التشغيل) =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209      # قناة المصدر (الأساسية)
PUBLIC_POST_CHANNEL = -1003554018307  # القناة الشغالة حالياً
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("mohammed_bot_v2", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات =====
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
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return res
    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

def init_db():
    db_query("""CREATE TABLE IF NOT EXISTS videos (
        v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, 
        poster_id TEXT, quality TEXT, duration TEXT, 
        status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0
    )""", fetch=False)
    # تحديث الأعمدة لضمان التوافق
    cols = [("ep_num","INTEGER"), ("poster_id","TEXT"), ("quality","TEXT"), ("duration","TEXT"), ("views","INTEGER DEFAULT 0"), ("status","TEXT DEFAULT 'waiting'"), ("title","TEXT")]
    for c, t in cols: db_query(f"ALTER TABLE videos ADD COLUMN IF NOT EXISTS {c} {t}", fetch=False)
    logging.info("✅ Database Initialized.")

# ===== أدوات معالجة النصوص وفك التشفير =====
def clean_and_decode(text):
    """تحويل 'ا . ل . م' إلى 'الم' وتنظيف الاسم"""
    if not text: return "مسلسل"
    cleaned = text.replace(".", "").replace(" ", "").strip()
    cleaned = re.sub(r'(الحلقة|حلقة).*', '', cleaned)
    return cleaned

def obfuscate_visual(text):
    """إعادة التشفير للنشر فقط (جمالياً)"""
    return " . ".join(list(text)) if text else ""

async def get_episodes_markup(title, current_v_id):
    """جلب أزرار الحلقات للمسلسل"""
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return []
    btns, row, seen = [], [], set()
    me = await app.get_me()
    for vid, ep in res:
        if ep in seen: continue
        seen.add(ep)
        label = f"✅ {ep}" if str(vid) == str(current_v_id) else f"{ep}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
        if len(row) == 5: btns.append(row); row = []
    if row: btns.append(row)
    return btns

# ===== المزامنة (Sync) للقناة الشغالة =====
@app.on_message(filters.command("sync") & filters.user(ADMIN_ID))
async def sync_handler(client, message):
    msg = await message.reply_text("🔄 جاري مزامنة القناة الحالية وفك التشفير...")
    count = 0
    try:
        async for m in client.get_chat_history(PUBLIC_POST_CHANNEL, limit=500):
            if m.caption and m.reply_markup:
                try:
                    url = m.reply_markup.inline_keyboard[0][0].url
                    if "start=" not in url: continue
                    v_id = url.split("start=")[1]
                    
                    title_match = re.search(r"المسلسل\s*:\s*(.*)\n", m.caption)
                    clean_t = clean_and_decode(title_match.group(1)) if title_match else "مسلسل"
                    
                    ep_m = re.search(r"رقم الحلقة\s*:\s*(\d+)", m.caption)
                    ep = int(ep_m.group(1)) if ep_m else 0
                    
                    db_query("""INSERT INTO videos (v_id, title, ep_num, status, poster_id) 
                               VALUES (%s, %s, %s, 'posted', %s) 
                               ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, status='posted'""",
                            (v_id, clean_t, ep, m.photo.file_id if m.photo else None, clean_t, ep), fetch=False)
                    count += 1
                except: continue
        await msg.edit_text(f"✅ تمت مزامنة {count} حلقة بنجاح.")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ أثناء المزامنة: {e}")

# ===== دالة الإرسال النهائية (المعالجة للأخطاء) =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    try:
        # إذا كان الاسم ناقصاً (قنوات محظورة)، نجذبه من السورس
        if not title or title == "مسلسل":
            try:
                m = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if m and m.caption:
                    title = clean_and_decode(m.caption)
                    ep_m = re.search(r'(\d+)', m.caption)
                    ep = int(ep_m.group(1)) if ep_m else ep
                    db_query("UPDATE videos SET title=%s, ep_num=%s, status='posted' WHERE v_id=%s", (title, ep, v_id), fetch=False)
            except: pass

        btns = await get_episodes_markup(title, v_id)
        
        # فحص الاشتراك
        is_sub = True
        try:
            member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
            if member.status in ["left", "kicked"]: is_sub = False
        except: is_sub = False

        cap = (f"<b>📺 المسلسل : {obfuscate_visual(title)}</b>\n"
               f"<b>🎞️ رقم الحلقة : {ep}</b>\n"
               f"<b>💿 الجودة : {q}</b>\n"
               f"<b>⏳ المدة : {dur}</b>\n\n🍿 مشاهدة ممتعة!")

        kb = []
        if not is_sub:
            kb.append([InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)])
        if btns:
            kb.extend(btns)

        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(kb))
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    except Exception as e:
        logging.error(f"❌ Error sending video {v_id}: {e}")
        await client.send_message(chat_id, "⚠️ عذراً، هذا الفيديو غير متوفر حالياً في المصدر.")

# ===== معالجات الرسائل (الرفع الجديد) =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المشاهدة! 👋")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        # محاولة أخيرة للفيديوهات غير المؤرشفة
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, "مسلسل", 0, "HD", "00:00")

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def handle_new_video(client, message):
    v_id = str(message.id)
    title = clean_and_decode(message.caption)
    db_query("INSERT INTO videos (v_id, title, status) VALUES (%s, %s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id, title), fetch=False)
    await message.reply_text("✅ تم استلام الفيديو. أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def handle_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    db_query("UPDATE videos SET poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.photo.file_id, res[0][0]), fetch=False)
    await message.reply_text("✅ أرسل الآن رقم الحلقة فقط:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "sync"]))
async def handle_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id, title, p_id = res[0]
    ep = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted', quality='HD' WHERE v_id=%s", (ep, v_id), fetch=False)
    
    me = await client.get_me()
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    await client.send_photo(PUBLIC_POST_CHANNEL, p_id, caption=f"🎬 <b>{obfuscate_visual(title)}</b>\nحلقة: {ep}", reply_markup=btn)
    await message.reply_text("🚀 تم النشر بنجاح!")

if __name__ == "__main__":
    init_db()
    app.run()
