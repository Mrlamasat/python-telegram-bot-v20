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

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الأساسية (Railway Variables) =====
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

# ===== دوال التنظيف والتحليل =====
def convert_ar_no(text):
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return text.translate(trans)

def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'[أإآأ]', 'ا', text)
    text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ى', 'ي', text)
    text = re.sub(r'^(ال)', '', text)
    text = re.sub(r'\s+', '', text)
    return text

def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text) # إزالة الروابط
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

# ===== نظام أزرار الحلقات الذكي =====
async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}"))
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔍 بحث", switch_inline_query_current_chat=""), InlineKeyboardButton("➕ طلب مسلسل", url="https://t.me/ramadan2206")])
    return buttons

# ===== الإرسال النهائي مع ميزة التصحيح التلقائي =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    try:
        # حل مشكلة Peer ID بالتعرف على القناة أولاً
        source_chat = await client.get_chat(int(SOURCE_CHANNEL))
        
        # تصحيح البيانات من المصدر (لحل مشكلة الحلقة 15 وغيرها)
        source_msg = await client.get_messages(source_chat.id, int(v_id))
        if source_msg and source_msg.caption:
            real_title = clean_series_title(source_msg.caption)
            ep_match = re.search(r'(\d+)', source_msg.caption)
            real_ep = int(ep_match.group(1)) if ep_match else ep
            # تحديث القاعدة بالبيانات الحية
            db_query("UPDATE videos SET title=%s, ep_num=%s, status='posted' WHERE v_id=%s", (real_title, real_ep, str(v_id)), fetch=False)
            title, ep = real_title, real_ep

    except Exception as e:
        logging.error(f"⚠️ Error fetching from source: {e}")

    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (str(v_id),), fetch=False)
    btns = await get_episodes_markup(title, v_id)
    
    try:
        is_sub = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        is_subscribed = is_sub.status not in ["left", "kicked"]
    except: is_subscribed = False

    cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ حلقة : {ep}</b>\n\n🍿 مشاهدة ممتعة!"
    
    if not is_subscribed:
        cap += "\n\n⚠️ <b>يجب الانضمام لمتابعة الحلقات 👇</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]] + (btns if btns else []))
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    await client.copy_message(chat_id, int(SOURCE_CHANNEL), int(v_id), caption=cap, reply_markup=markup)

# ===== محرك البحث الذكي =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats", "del", "import_all"]))
async def smart_search(client, message):
    raw_input = convert_ar_no(message.text)
    ep_match = re.search(r'\d+', raw_input)
    target_ep = ep_match.group() if ep_match else None
    query_norm = normalize_text(re.sub(r'\d+', '', raw_input))

    all_titles_res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    if not all_titles_res: return
    all_titles = [r[0] for r in all_titles_res]
    
    matches = [t for t in all_titles if query_norm in normalize_text(t)]

    if matches:
        title = matches[0]
        video_res = db_query("SELECT v_id, quality, duration FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, int(target_ep) if target_ep else 1))
        if video_res:
            v_id, q, dur = video_res[0]
            await send_video_final(client, message.chat.id, message.from_user.id, v_id, title, target_ep or 1, q, dur)
        else:
            # عرض الحلقات المتوفرة إذا لم نجد الرقم المطلوب
            btns = await get_episodes_markup(title, 0)
            await message.reply_text(f"🎬 مسلسل **{title}** متوفر، اختر الحلقة:", reply_markup=InlineKeyboardMarkup(btns))
    else:
        # هل تقصد؟
        norm_map = {normalize_text(t): t for t in all_titles}
        close = difflib.get_close_matches(query_norm, list(norm_map.keys()), n=1, cutoff=0.5)
        if close:
            suggested = norm_map[close[0]]
            await message.reply_text(f"❓ هل تقصد: **{suggested}**؟", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ نعم", callback_data=f"c_{close[0]}")]]))

# ===== معالجة روابط Start =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("مرحباً بك! ابحث عن مسلسلك المفضل بكتابة اسمه..")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        # جلب تلقائي إذا كان المعرف غير مسجل
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, "جاري الجلب...", 1, "HD", "00:00")

# ===== أمر للأدمن لجلب كافة الحلقات من القناة (لإصلاح النقص) =====
@app.on_message(filters.command("import_all") & filters.user(ADMIN_ID))
async def import_all(client, message):
    await message.reply_text("⏳ جاري أرشفة حلقات القناة المصدر وتوحيد الأسماء...")
    async for msg in client.get_chat_history(SOURCE_CHANNEL, limit=200):
        if msg.caption:
            v_id = str(msg.id)
            title = clean_series_title(msg.caption)
            ep_match = re.search(r'(\d+)', msg.caption)
            ep = int(ep_match.group(1)) if ep_match else 1
            db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s", (v_id, title, ep, title, ep), fetch=False)
    await message.reply_text("✅ تمت الأرشفة بنجاح! جميع الحلقات الآن متوفرة في الأزرار.")

if __name__ == "__main__":
    # تهيئة الجداول
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, poster_id TEXT, quality TEXT, duration TEXT, status TEXT DEFAULT 'posted', views INTEGER DEFAULT 0)", fetch=False)
    logging.info("🚀 Bot is running...")
    app.run()
