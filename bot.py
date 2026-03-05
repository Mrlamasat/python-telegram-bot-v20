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

# ===== وظائف المعالجة الذكية =====
def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text)
    # تنظيف العنوان ليبقى اسم المسلسل فقط
    text = re.sub(r'(الحلقة|حلقة)?\s*\d+|\[.*?\]|الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep_num(text):
    if not text: return 1
    match = re.search(r'(?:الحلقة|حلقة|#)?\s*(\d+)', text)
    return int(match.group(1)) if match else 1

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

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

# ===== نظام الأرشفة التلقائية (للحلقات الجديدة) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def auto_archive_video(client, message):
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO NOTHING", (str(message.id),), fetch=False)

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def auto_archive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status = 'waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    cap = message.caption or ""
    title, ep = clean_series_title(cap), extract_ep_num(cap)
    db_query("UPDATE videos SET title=%s, ep_num=%s, status='posted' WHERE v_id=%s", (title, ep, v_id), fetch=False)
    
    me = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ شاهد الحلقة الآن", url=f"https://t.me/{me.username}?start={v_id}")]])
    await client.send_photo(PUBLIC_POST_CHANNEL, message.photo.file_id, caption=f"🎬 <b>{safe_t}</b>\n📌 <b>الحلقة: {ep}</b>", reply_markup=markup)

# ===== أمر الأرشفة الجماعية المطور (للأدمن - لا يسبب تعليق) =====
@app.on_message(filters.command("archive") & filters.user(ADMIN_ID))
async def bulk_archive(client, message):
    status_msg = await message.reply_text("⏳ بدأت الأرشفة الذكية في الخلفية...\nيمكنك استخدام البوت الآن وسأقوم بتحديثك كل 10 حلقات.")
    
    count = 0
    last_video_id = None
    
    try:
        async for msg in client.get_chat_history(SOURCE_CHANNEL, limit=1000):
            # هذا السطر يسمح للبوت بمعالجة الأوامر الأخرى أثناء الأرشفة
            await asyncio.sleep(0.1) 
            
            if msg.video or msg.document or msg.animation:
                last_video_id = str(msg.id)
            elif msg.photo and last_video_id:
                cap = msg.caption or ""
                title, ep = clean_series_title(cap), extract_ep_num(cap)
                db_query("""
                    INSERT INTO videos (v_id, title, ep_num, status) 
                    VALUES (%s, %s, %s, 'posted') 
                    ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s
                """, (last_video_id, title, ep, title, ep), fetch=False)
                last_video_id = None
                count += 1
                
                if count % 10 == 0:
                    try: await status_msg.edit_text(f"⏳ جاري الأرشفة... تم حفظ {count} حلقة حتى الآن.")
                    except: pass

        await status_msg.edit_text(f"✅ اكتملت أرشفة الحلقات القديمة!\nتم تسجيل {count} حلقة بنجاح في قاعدة البيانات.")
    except Exception as e:
        logging.error(f"Archive Error: {e}")
        await message.reply_text(f"❌ حدث خطأ أثناء الأرشفة: {e}")

# ===== Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"مرحباً بك يا <b>{escape(message.from_user.first_name)}</b>!")
    
    v_id_key = message.command[1]
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id_key,))
    if not res: return await message.reply_text("❌ عذراً، هذه الحلقة غير مسجلة حالياً.")
    
    title, ep = res[0]
    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        try:
            m = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
            if m.status in ["left", "kicked"]:
                return await message.reply_text("⚠️ يجب الانضمام للقناة لمشاهدة الحلقة 👇", 
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        except: pass

    btns = await get_episodes_markup(title, v_id_key)
    safe_t = obfuscate_visual(escape(title))
    cap = f"📺 <b>{safe_t}</b>\n🎞️ <b>الحلقة: {ep}</b>"
    
    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id_key), caption=cap, reply_markup=InlineKeyboardMarkup(btns))
    except Exception as e:
        logging.error(f"Copy error: {e}")
        await message.reply_text("❌ فشل جلب الفيديو، تأكد من وجوده في قناة المصدر.")

if __name__ == "__main__":
    # تنظيف وبناء القاعدة من جديد لضمان الاستقرار
    db_query("DROP TABLE IF EXISTS videos", fetch=False)
    db_query("CREATE TABLE videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, status TEXT)", fetch=False)
    logging.info("🚀 تم تصفير القاعدة وبدء التشغيل...")
    app.run()
