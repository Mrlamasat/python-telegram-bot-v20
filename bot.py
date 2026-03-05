import os
import psycopg2
import logging
import re
import asyncio
from urllib.parse import quote
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

# ===== Logging =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== Environment Variables =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHtplbFHhJ-4fatqVWXQowETrKg-u0cr0Q")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003790915936
FORCE_SUB_LINK = "https://t.me/+KyrbVyp0QCJhZGU8"
PUBLIC_POST_CHANNEL = -1003678294148

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ذاكرة مؤقتة لتقليل الضغط
EPISODES_CACHE = {}

# ===== Database (للمشاهدات والإحصائيات) =====
def db_query(query, params=(), fetch=True):
    if not DATABASE_URL: return None
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
    match = re.search(r'(?:الحلقة|حلقة|#|EP)\s*(\d+)', text, re.IGNORECASE)
    if match: return int(match.group(1))
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 1

# ===== محرك جلب الحلقات (Live Search) =====
async def fetch_live_episodes(v_id):
    v_id = int(v_id)
    if v_id in EPISODES_CACHE: return EPISODES_CACHE[v_id]

    try:
        # 1. البحث عن البوستر المشترك (الصورة قبل الفيديو)
        poster_unique_id = None
        for i in range(1, 6): # فحص آخر 5 رسائل قبل الفيديو
            try:
                m = await app.get_messages(SOURCE_CHANNEL, v_id - i)
                if m and m.photo:
                    poster_unique_id = m.photo.file_unique_id
                    break
            except: continue
        
        if not poster_unique_id: return []

        # 2. مسح المنطقة المحيطة لإيجاد الحلقات التي لها نفس البوستر
        found = []
        search_range = list(range(max(1, v_id - 100), v_id + 100))
        messages = await app.get_messages(SOURCE_CHANNEL, search_range)
        
        last_poster_id = None
        for m in messages:
            if not m or m.empty: continue
            if m.photo:
                last_poster_id = m.photo.file_unique_id
            elif (m.video or m.document or m.animation):
                # إذا كان الفيديو يتبع نفس البوستر
                if last_poster_id == poster_unique_id:
                    ep_no = extract_ep(m.caption or "")
                    found.append((m.id, ep_no))
        
        final = sorted(list(set(found)), key=lambda x: x[1])
        EPISODES_CACHE[v_id] = final
        return final
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return []
    except Exception as e:
        logging.error(f"Live Search Error: {e}")
        return []

async def get_episodes_markup(v_id, title, current_ep):
    episodes = await fetch_live_episodes(v_id)
    buttons, row = [], []
    bot = await app.get_me()

    if episodes:
        for m_id, ep_no in episodes:
            label = f"✅ {ep_no}" if int(m_id) == int(v_id) else f"{ep_no}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot.username}?start={m_id}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row: buttons.append(row)

    # أزرار المشاركة
    share_url = f"https://t.me/{bot.username}?start={v_id}"
    tg_share = f"https://t.me/share/url?url={quote(share_url)}&text={quote(f'🎬 {title} - حلقة {current_ep}')}"
    
    buttons.append([InlineKeyboardButton("📢 مشاركة الحلقة", url=tg_share)])
    return InlineKeyboardMarkup(buttons)

# ===== Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا <b>{message.from_user.first_name}</b>\nأرسل رابط أي حلقة من القناة لمشاهدتها هنا.")
    
    v_id = message.command[1]
    
    # التحقق من الاشتراك الإجباري
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        if member.status in ["left", "kicked"]:
            return await message.reply_text(
                "⚠️ <b>يجب عليك الاشتراك في القناة أولاً لمشاهدة الحلقة</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=FORCE_SUB_LINK)]])
            )
    except: pass

    try:
        # جلب معلومات الفيديو مباشرة
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not msg or msg.empty:
            return await message.reply_text("❌ هذه الحلقة غير موجودة أو تم حذفها.")

        # تنظيف العنوان
        raw_cap = msg.caption or "مسلسل"
        title = re.sub(r'(الحلقة|حلقة|#|EP)?\s*\d+.*', '', raw_cap, flags=re.IGNORECASE).strip()
        ep_no = extract_ep(raw_cap)
        
        # إنشاء الأزرار
        markup = await get_episodes_markup(v_id, title, ep_no)
        
        safe_title = " . ".join(list(title)) # تجميل العنوان كما طلبت سابقاً
        cap = f"📺 <b>{safe_title}</b>\n🎞️ <b>الحلقة: {ep_no}</b>\n\nنتمنى لكم مشاهدة ممتعة."
        
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=cap,
            reply_markup=markup
        )
        
        # تسجيل مشاهدة في القاعدة (اختياري)
        db_query("INSERT INTO videos (v_id, views) VALUES (%s, 1) ON CONFLICT (v_id) DO UPDATE SET views = videos.views + 1", (v_id,), fetch=False)

    except Exception as e:
        logging.error(f"Start Error: {e}")
        await message.reply_text("❌ حدث خطأ أثناء جلب الحلقة.")

if __name__ == "__main__":
    # إنشاء جدول المشاهدات إذا لم يوجد
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, views INTEGER DEFAULT 0)", fetch=False)
    app.run()
