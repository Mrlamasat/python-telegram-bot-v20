import os
import psycopg2
import logging
import re
import urllib.parse
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

# ===== Logging =====
logging.basicConfig(level=logging.INFO)

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

# ذاكرة مؤقتة لتقليل الطلبات على تيليجرام (تجنب الـ Flood)
EPISODES_CACHE = {}

# ===== Database =====
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

# ===== وظيفة استخراج رقم الحلقة بدقة =====
def extract_ep(text):
    if not text: return 1
    match = re.search(r'(?:الحلقة|حلقة|#|EP)\s*(\d+)', text, re.IGNORECASE)
    if match: return int(match.group(1))
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 1

# ===== محرك جلب الحلقات من المصدر (Live Search) =====
async def fetch_live_episodes(v_id):
    """تجلب الحلقات مباشرة من القناة بناءً على البوستر المشترك"""
    v_id = int(v_id)
    if v_id in EPISODES_CACHE: return EPISODES_CACHE[v_id]

    try:
        # 1. البحث عن البوستر (الصورة) قبل الفيديو
        poster_id = None
        for i in range(1, 11):
            m = await app.get_messages(SOURCE_CHANNEL, v_id - i)
            if m and m.photo:
                poster_id = m.photo.file_unique_id
                break
        
        if not poster_id: return []

        # 2. مسح الرسائل المحيطة (100 رسالة)
        found = []
        search_ids = list(range(max(1, v_id - 70), v_id + 70))
        messages = await app.get_messages(SOURCE_CHANNEL, search_ids)
        
        current_p = None
        for m in messages:
            if not m or m.empty: continue
            if m.photo: current_p = m.photo.file_unique_id
            elif (m.video or m.document) and current_p == poster_id:
                ep_no = extract_ep(m.caption)
                found.append((m.id, ep_no))
        
        # ترتيب وتخزين في الكاش
        final = sorted(list(set(found)), key=lambda x: x[1])
        EPISODES_CACHE[v_id] = final
        return final
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return []
    except: return []

async def get_episodes_markup(v_id, title, current_ep):
    # جلب الحلقات من المصدر مباشرة
    episodes = await fetch_live_episodes(v_id)
    if not episodes: return None
    
    buttons, row = [], []
    bot = await app.get_me()

    for m_id, ep_no in episodes:
        label = f"▶️ {ep_no}" if int(m_id) == int(v_id) else f"{ep_no}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot.username}?start={m_id}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    # أزرار المشاركة
    share_url = f"https://t.me/{bot.username}?start={v_id}"
    tg_share = f"https://t.me/share/url?url={urllib.parse.quote(share_url)}&text={urllib.parse.quote(f'🎬 {title} - حلقة {current_ep}')}"
    
    buttons.append([InlineKeyboardButton("📢 مشاركة تليجرام", url=tg_share)])
    return buttons

# ===== Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد! أرسل رابط الحلقة لمشاهدتها.")
    
    v_id = message.command[1]
    
    # التحقق من الاشتراك
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        if member.status in ["left", "kicked"]:
            return await message.reply_text("⚠️ اشترك أولاً:", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=FORCE_SUB_LINK)]]))
    except: pass

    # جلب معلومات الفيديو من القناة مباشرة لضمان الدقة
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        title = re.sub(r'(الحلقة|حلقة)?\s*\d+.*', '', msg.caption or "مسلسل", flags=re.IGNORECASE).strip()
        ep_no = extract_ep(msg.caption)
        
        markup = await get_episodes_markup(v_id, title, ep_no)
        
        cap = f"الحلقة [{ep_no}]\n\n{title}\n\nنتمنى لكم مشاهده ممتعة."
        
        await client.copy_message(
            message.chat.id, 
            SOURCE_CHANNEL, 
            int(v_id), 
            caption=cap, 
            reply_markup=InlineKeyboardMarkup(markup) if markup else None
        )
    except Exception as e:
        await message.reply_text("❌ الحلقة غير متوفرة حالياً.")

if __name__ == "__main__":
    app.run()
