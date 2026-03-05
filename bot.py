import os
import psycopg2
import psycopg2.pool
import logging
import re
import asyncio
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات =====
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

# ===== قاعدة البيانات (Pool) =====
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
        logging.error(f"❌ Database Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn:
            try: get_pool().putconn(conn)
            except: pass

# ===== وظائف التنظيف واستخراج البيانات =====
def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(الحلقة|حلقة)?\s*\d+|\[.*?\]|الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n+', ' ', text)
    return text.strip()

def extract_ep_num(text):
    if not text: return 0
    match = re.search(r'(?:الحلقة|حلقة|#)?\s*(\d+)', text)
    return int(match.group(1)) if match else 0

def get_series_signature(caption):
    if not caption: return ""
    signature = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', caption, flags=re.IGNORECASE)
    signature = re.sub(r'\s+', ' ', signature).strip()
    return signature

# ===== نظام الأرشفة والمسح الشامل =====
async def scan_all_episodes(client, start_v_id):
    try:
        v_id_int = int(start_v_id)
        first_msg = await client.get_messages(SOURCE_CHANNEL, v_id_int)
        if not first_msg or first_msg.empty: return 0
        
        series_signature = ""
        # محاولة العثور على بوستر في الـ 5 رسائل السابقة
        for i in range(1, 6):
            prev_msg = await client.get_messages(SOURCE_CHANNEL, v_id_int - i)
            if prev_msg and not prev_msg.empty and prev_msg.photo:
                series_signature = get_series_signature(prev_msg.caption)
                break
        
        if not series_signature and first_msg.caption:
            series_signature = get_series_signature(first_msg.caption)
        
        if not series_signature: return 0
        
        found_count = 0
        # نطاق البحث (يمكن تعديله حسب حجم القناة)
        search_range = 200 
        search_ids = [i for i in range(v_id_int - search_range, v_id_int + search_range)]
        
        # جلب الرسائل على دفعات (batches) لتسريع العملية
        for i in range(0, len(search_ids), 100):
            batch = search_ids[i:i+100]
            messages = await client.get_messages(SOURCE_CHANNEL, batch)
            for m in messages:
                if m and (m.video or m.document) and m.caption:
                    if get_series_signature(m.caption) == series_signature:
                        ep_num = extract_ep_num(m.caption)
                        if ep_num > 0:
                            db_query("""
                                INSERT INTO videos (v_id, title, ep_num, status) 
                                VALUES (%s, %s, %s, 'posted')
                                ON CONFLICT (v_id) DO NOTHING
                            """, (str(m.id), series_signature[:100], ep_num), fetch=False)
                            found_count += 1
        return found_count
    except Exception as e:
        logging.error(f"Scan Error: {e}")
        return 0

async def auto_archive_logic(client, v_id_key):
    try:
        v_id_int = int(v_id_key)
        msg = await client.get_messages(SOURCE_CHANNEL, v_id_int)
        if not msg or msg.empty: return None

        title = clean_series_title(msg.caption) if msg.caption else "مسلسل"
        ep = extract_ep_num(msg.caption) if msg.caption else 0
        
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status) 
            VALUES (%s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, status='posted'
        """, (v_id_key, title, ep, title, ep), fetch=False)
        
        # المسح الشامل في الخلفية
        asyncio.create_task(scan_all_episodes(client, v_id_key))
        return (title, ep)
    except Exception as e:
        logging.error(f"Archive Error: {e}")
        return None

# ===== توليد أزرار الحلقات (Pagination) =====
async def get_episodes_markup(title, current_v_id, page=0):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res or len(res) <= 1: return []
    
    all_buttons = []
    seen = set()
    for v_id, ep_num in res:
        if ep_num in seen: continue
        seen.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        all_buttons.append(InlineKeyboardButton(label, callback_data=f"ep_{v_id}"))
    
    items_per_page = 10
    total_pages = (len(all_buttons) + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    current_batch = all_buttons[start_idx : start_idx + items_per_page]
    
    btns = []
    for i in range(0, len(current_batch), 5):
        btns.append(current_batch[i:i+5])
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"page_{title}_{page-1}_{current_v_id}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="info"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"page_{title}_{page+1}_{current_v_id}"))
    
    if nav: btns.append(nav)
    return btns

# ===== المعالجات (Handlers) =====
@app.on_callback_query()
async def handle_callback(client: Client, query: CallbackQuery):
    data = query.data
    if data.startswith("ep_"):
        v_id = data.replace("ep_", "")
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
        if not res: return await query.answer("الحلقة غير موجودة")
        
        title, ep = res[0]
        btns = await get_episodes_markup(title, v_id)
        safe_title = " . ".join(list(title[:30])) # توزيع الحروف
        cap = f"📺 <b>{safe_title}</b>\n🎞️ <b>الحلقة: {ep}</b>"
        
        try:
            await query.message.delete()
            await client.copy_message(query.message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))
            db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
        except:
            await query.answer("خطأ في جلب الفيديو")
            
    elif data.startswith("page_"):
        _, title, page, v_id = data.split("_")
        btns = await get_episodes_markup(title, v_id, int(page))
        await query.message.edit_reply_markup(InlineKeyboardMarkup(btns))
        
    await query.answer()

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"مرحباً بك يا محمد في بوت الحلقات.")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
    
    if not res:
        archive_res = await auto_archive_logic(client, v_id)
        if not archive_res: return await message.reply_text("الفيديو غير متاح")
        title, ep = archive_res
    else:
        title, ep = res[0]

    # فحص الاشتراك
    if message.from_user.id != ADMIN_ID:
        try:
            m = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
            if m.status in ["left", "kicked"]:
                return await message.reply_text("⚠️ اشترك أولاً:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        except: pass

    btns = await get_episodes_markup(title, v_id)
    safe_title = " . ".join(list(title[:30]))
    cap = f"📺 <b>{safe_title}</b>\n🎞️ <b>الحلقة: {ep}</b>"
    
    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns) if btns else None)
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, status TEXT, views INTEGER DEFAULT 0)", fetch=False)
    logging.info("🚀 Bot is running...")
    app.run()
