import os
import psycopg2
import logging
import re
import asyncio
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الأساسية =====
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

# ===== قاعدة البيانات =====
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
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== وظائف التنظيف والاستخراج =====
def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(الحلقة|حلقة)?\s*\d+|\[.*?\]|الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep_num(text):
    match = re.search(r'(?:الحلقة|حلقة|#)?\s*(\d+)', text)
    return int(match.group(1)) if match else 1

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return []
    btns, row, seen = [], [], set()
    me = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen: continue
        seen.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={v_id}"))
        if len(row) == 5: btns.append(row); row = []
    if row: btns.append(row)
    return btns

# ===== نظام الأرشفة الذكي (يعمل مع الرسائل الجديدة والمحولة) =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def handle_video(client, message):
    # نأخذ ID الرسالة الأصلية دائماً
    real_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO NOTHING", (real_id,), fetch=False)
    logging.info(f"📹 تم رصد فيديو بـ ID: {real_id}")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def handle_photo(client, message):
    # البحث عن آخر فيديو مسجل "ينتظر"
    res = db_query("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    
    video_id = res[0][0]
    cap = message.caption or ""
    title, ep = clean_series_title(cap), extract_ep_num(cap)
    
    db_query("UPDATE videos SET title=%s, ep_num=%s, status='posted' WHERE v_id=%s", (title, ep, video_id), fetch=False)
    
    # النشر التلقائي (اختياري، يمكنك حذفه إذا كنت لا تريد تكرار النشر)
    me = await client.get_me()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=f"https://t.me/{me.username}?start={video_id}")]])
    try:
        await client.send_photo(PUBLIC_POST_CHANNEL, message.photo.file_id, caption=f"🎬 <b>{title}</b>\n📌 حلقة: {ep}", reply_markup=markup)
    except: pass
    logging.info(f"✅ تم ربط الفيديو {video_id} بمسلسل {title} حلقة {ep}")

# ===== Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2: return await message.reply_text("أهلاً بك!")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
    if not res: return await message.reply_text("❌ هذه الحلقة غير متوفرة في الأرشيف حالياً.")
    
    title, ep = res[0]
    
    # استثناء الأدمن من فحص الاشتراك
    if message.from_user.id != ADMIN_ID:
        try:
            m = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
            if m.status in ["left", "kicked"]:
                return await message.reply_text("⚠️ اشترك لمشاهدة الحلقة 👇", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        except: pass

    btns = await get_episodes_markup(title, v_id)
    cap = f"📺 <b>{escape(title)}</b>\n🎞️ <b>الحلقة: {ep}</b>"
    
    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))
    except Exception as e:
        logging.error(f"Copy Error: {e}")
        await message.reply_text("❌ لم نتمكن من العثور على ملف الفيديو. تأكد من وجوده في السورس.")

if __name__ == "__main__":
    # لا نقوم بمسح القاعدة كل مرة الآن للحفاظ على ما تمت أرشفته
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, status TEXT)", fetch=False)
    app.run()
