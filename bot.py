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
        if conn: get_pool().putconn(conn)

# ===== وظائف التنظيف والاستخراج =====
def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(الحلقة|حلقة)?\s*\d+|\[.*?\]|الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep_num(text):
    if not text: return 0
    match = re.search(r'(?:الحلقة|حلقة|#)?\s*(\d+)', text)
    return int(match.group(1)) if match else 0

async def scan_all_episodes(client, series_title, start_v_id):
    """مسح جميع حلقات المسلسل وإضافتها إلى قاعدة البيانات"""
    try:
        logging.info(f"🔍 بدء مسح جميع حلقات المسلسل: {series_title}")
        v_id_int = int(start_v_id)
        
        # البحث في الاتجاهين (قبل وبعد)
        found_episodes = {}
        
        # البحث للأمام (الرسائل الأحدث)
        current_id = v_id_int + 1
        found_count = 0
        while found_count < 30:  # حد أقصى 30 حلقة
            try:
                msg = await client.get_messages(SOURCE_CHANNEL, current_id)
                if msg and not msg.empty:
                    # التحقق إذا كانت هذه حلقة من نفس المسلسل
                    if msg.video or msg.document:
                        # استخراج العنوان ورقم الحلقة
                        caption = msg.caption or ""
                        msg_title = clean_series_title(caption)
                        msg_ep = extract_ep_num(caption)
                        
                        # إذا كان العنوان مشابهاً للمسلسل
                        if msg_title == series_title and msg_ep > 0:
                            found_episodes[msg_ep] = current_id
                            logging.info(f"✅ تم العثور على حلقة {msg_ep} (ID: {current_id})")
                            
                            # حفظ في قاعدة البيانات
                            db_query("""
                                INSERT INTO videos (v_id, title, ep_num, status) 
                                VALUES (%s, %s, %s, 'posted')
                                ON CONFLICT (v_id) DO NOTHING
                            """, (str(current_id), series_title, msg_ep), fetch=False)
                current_id += 1
                found_count += 1
            except:
                break
        
        # البحث للخلف (الرسائل الأقدم)
        current_id = v_id_int - 1
        found_count = 0
        while found_count < 30 and current_id > 0:
            try:
                msg = await client.get_messages(SOURCE_CHANNEL, current_id)
                if msg and not msg.empty:
                    if msg.video or msg.document:
                        caption = msg.caption or ""
                        msg_title = clean_series_title(caption)
                        msg_ep = extract_ep_num(caption)
                        
                        if msg_title == series_title and msg_ep > 0:
                            found_episodes[msg_ep] = current_id
                            logging.info(f"✅ تم العثور على حلقة {msg_ep} (ID: {current_id})")
                            
                            db_query("""
                                INSERT INTO videos (v_id, title, ep_num, status) 
                                VALUES (%s, %s, %s, 'posted')
                                ON CONFLICT (v_id) DO NOTHING
                            """, (str(current_id), series_title, msg_ep), fetch=False)
                current_id -= 1
                found_count += 1
            except:
                break
        
        logging.info(f"📊 تم العثور على إجمالي {len(found_episodes)} حلقة للمسلسل {series_title}")
        return len(found_episodes)
        
    except Exception as e:
        logging.error(f"خطأ في مسح الحلقات: {e}")
        return 0

# ===== محرك الأرشفة التلقائية =====
async def auto_archive_logic(client, v_id_key):
    try:
        v_id_int = int(v_id_key)
        
        # جلب الفيديو نفسه أولاً
        msg = await client.get_messages(SOURCE_CHANNEL, v_id_int)
        if not msg or msg.empty: 
            return None

        title = "مسلسل مستعاد"
        ep = 0
        
        # استخراج البيانات من الفيديو نفسه
        if msg.caption:
            title = clean_series_title(msg.caption)
            ep = extract_ep_num(msg.caption)
        
        # إذا لم نجد بيانات، نبحث في الرسائل المحيطة
        if ep == 0:
            # البحث في الرسائل التالية
            next_ids = [i for i in range(v_id_int + 1, v_id_int + 11)]
            next_messages = await client.get_messages(SOURCE_CHANNEL, next_ids)
            
            for m in next_messages:
                if not m or m.empty:
                    continue
                    
                if m.photo and m.caption:
                    title = clean_series_title(m.caption)
                    if ep == 0:
                        ep = extract_ep_num(m.caption)
                elif m.text:
                    if m.text.isdigit():
                        ep = int(m.text)
                        break
                    elif "الحلقة" in m.text or "حلقة" in m.text:
                        extracted_ep = extract_ep_num(m.text)
                        if extracted_ep > 0:
                            ep = extracted_ep
                            break
        
        # حفظ الحلقة الحالية
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status) 
            VALUES (%s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, status='posted'
        """, (v_id_key, title, ep, title, ep), fetch=False)
        
        # بدء مسح جميع الحلقات في الخلفية
        asyncio.create_task(scan_all_episodes(client, title, v_id_key))
        
        return (title, ep)
        
    except Exception as e:
        logging.error(f"Archive Logic Error: {e}")
        return None

async def get_episodes_markup(title, current_v_id, page=0):
    """الحصول على أزرار الحلقات من قاعدة البيانات"""
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    
    if not res or len(res) <= 1:  # إذا كانت هناك حلقة واحدة فقط
        return [[InlineKeyboardButton("🔄 جاري تحميل الحلقات...", callback_data="loading")]]
    
    btns, row, seen = [], [], set()
    
    # تجهيز جميع الأزرار
    all_buttons = []
    for v_id, ep_num in res:
        if ep_num in seen: continue
        seen.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        all_buttons.append(InlineKeyboardButton(label, callback_data=f"ep_{v_id}"))
    
    # عرض 8 أزرار في كل صفحة
    items_per_page = 8
    total_pages = (len(all_buttons) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(all_buttons))
    current_buttons = all_buttons[start_idx:end_idx]
    
    # تقسيم إلى صفوف (4 أزرار لكل صف)
    for i in range(0, len(current_buttons), 4):
        row_buttons = current_buttons[i:i+4]
        btns.append(row_buttons)
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"page_{title}_{page-1}_{current_v_id}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="info"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"page_{title}_{page+1}_{current_v_id}"))
    
    if nav_buttons:
        btns.append(nav_buttons)
    
    return btns

# ===== معالج الضغط على الأزرار =====
@app.on_callback_query()
async def handle_callback(client: Client, query: CallbackQuery):
    data = query.data
    
    if data == "loading":
        await query.answer("🔄 جاري تحميل قائمة الحلقات...", show_alert=False)
        return
    
    if data.startswith("ep_"):
        v_id = data.replace("ep_", "")
        
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
        if not res:
            await query.answer("❌ هذه الحلقة غير متوفرة", show_alert=True)
            return
        
        title, ep = res[0]
        
        # التحقق من وجود حلقات أخرى
        check_other = db_query("SELECT COUNT(*) FROM videos WHERE title = %s", (title,))
        if check_other and check_other[0][0] <= 1:
            # إذا كانت هذه أول حلقة فقط، نبدأ المسح
            asyncio.create_task(scan_all_episodes(client, title, v_id))
        
        btns = await get_episodes_markup(title, v_id)
        
        safe_title = " . ".join(list(title))
        cap = f"📺 <b>{safe_title}</b>\n🎞️ <b>الحلقة: {ep}</b>"
        
        try:
            await query.message.delete()
            await client.copy_message(
                query.message.chat.id, 
                SOURCE_CHANNEL, 
                int(v_id), 
                caption=cap, 
                reply_markup=InlineKeyboardMarkup(btns)
            )
            db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
            await query.answer()
        except Exception as e:
            logging.error(f"Copy message error: {e}")
            await query.answer("❌ الفيديو غير متوفر", show_alert=True)
    
    elif data.startswith("page_"):
        parts = data.split("_")
        title = parts[1]
        page = int(parts[2])
        current_v_id = parts[3]
        
        btns = await get_episodes_markup(title, current_v_id, page)
        await query.message.edit_reply_markup(InlineKeyboardMarkup(btns))
        await query.answer()
    
    elif data == "info":
        await query.answer("استخدم الأزرار للتنقل بين الحلقات", show_alert=False)

# ===== Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك في بوت الحلقات.")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
    
    if not res:
        archive_res = await auto_archive_logic(client, v_id)
        if not archive_res:
            return await message.reply_text("❌ عذراً، لم يتم العثور على بيانات الحلقة في السورس.")
        title, ep = archive_res
    else:
        title, ep = res[0]

    # فحص الاشتراك
    if message.from_user.id != ADMIN_ID:
        try:
            m = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
            if m.status in ["left", "kicked"]:
                return await message.reply_text("⚠️ اشترك لمشاهدة الحلقة 👇", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        except: pass

    # التحقق من وجود حلقات أخرى
    check_other = db_query("SELECT COUNT(*) FROM videos WHERE title = %s", (title,))
    if check_other and check_other[0][0] <= 1:
        # إذا كانت هذه أول حلقة فقط، نبدأ المسح التلقائي
        asyncio.create_task(scan_all_episodes(client, title, v_id))
    
    btns = await get_episodes_markup(title, v_id, page=0)
    
    safe_title = " . ".join(list(title))
    cap = f"📺 <b>{safe_title}</b>\n🎞️ <b>الحلقة: {ep}</b>"
    
    try:
        await client.copy_message(
            message.chat.id, 
            SOURCE_CHANNEL, 
            int(v_id), 
            caption=cap, 
            reply_markup=InlineKeyboardMarkup(btns)
        )
        db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    except Exception as e:
        logging.error(f"Copy message error: {e}")
        await message.reply_text("❌ الفيديو غير موجود حالياً في قناة السورس.")

if __name__ == "__main__":
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, 
            title TEXT, 
            ep_num INTEGER, 
            status TEXT, 
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    logging.info("🚀 البوت يعمل الآن مع مسح تلقائي لجميع الحلقات...")
    app.run()
