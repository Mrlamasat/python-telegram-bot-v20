import os
import psycopg2
import logging
import re
import asyncio
from urllib.parse import quote
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

# ===== إعداد السجلات =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== سحب الإعدادات من الاستضافة (Variables) =====
# تأكد من إضافة هذه الأسماء في خانة Variables في Railway
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN") # سيتم سحبه تلقائياً من الاستضافة
DATABASE_URL = os.environ.get("DATABASE_URL")

# المعرفات الثابتة (أو يمكنك سحبها أيضاً من الاستضافة بنفس الطريقة)
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003790915936
FORCE_SUB_LINK = "https://t.me/+KyrbVyp0QCJhZGU8"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# كاش مؤقت
EPISODES_CACHE = {}

# ===== قاعدة البيانات =====
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

# ===== محرك البحث الحي (يربط الحلقات ببعضها عبر البوستر) =====
async def fetch_live_episodes(v_id):
    v_id = int(v_id)
    if v_id in EPISODES_CACHE: return EPISODES_CACHE[v_id]

    try:
        poster_unique_id = None
        for i in range(1, 6):
            try:
                m = await app.get_messages(SOURCE_CHANNEL, v_id - i)
                if m and m.photo:
                    poster_unique_id = m.photo.file_unique_id
                    break
            except: continue
        
        if not poster_unique_id: return []

        found = []
        # فحص محيط 100 رسالة لإيجاد باقي الحلقات
        search_ids = list(range(max(1, v_id - 100), v_id + 100))
        messages = await app.get_messages(SOURCE_CHANNEL, search_ids)
        
        last_p_id = None
        for m in messages:
            if not m or m.empty: continue
            if m.photo:
                last_p_id = m.photo.file_unique_id
            elif (m.video or m.document or m.animation):
                if last_p_id == poster_unique_id:
                    ep_no = extract_ep(m.caption or "")
                    found.append((m.id, ep_no))
        
        final = sorted(list(set(found)), key=lambda x: x[1])
        EPISODES_CACHE[v_id] = final
        return final
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return []
    except: return []

async def get_episodes_markup(v_id, title, current_ep):
    episodes = await fetch_live_episodes(v_id)
    buttons, row = [], []
    bot = await app.get_me()

    if episodes:
        for m_id, ep_no in episodes:
            label = f"✅ {ep_no}" if int(m_id) == int(v_id) else f"{ep_no}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot.username}?start={m_id}"))
            if len(row) == 5:
                buttons.append(row); row = []
        if row: buttons.append(row)

    share_url = f"https://t.me/{bot.username}?start={v_id}"
    tg_share = f"https://t.me/share/url?url={quote(share_url)}&text={quote(f'🎬 {title} - حلقة {current_ep}')}"
    buttons.append([InlineKeyboardButton("📢 مشاركة الحلقة", url=tg_share)])
    
    return InlineKeyboardMarkup(buttons)

# ===== Start Handler =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا <b>{message.from_user.first_name}</b> في بوت الحلقات.")
    
    v_id = message.command[1]
    
    # التحقق من الاشتراك
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        if member.status in ["left", "kicked"]:
            return await message.reply_text(
                "⚠️ <b>يجب الاشتراك في القناة أولاً لمتابعة المشاهدة</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=FORCE_SUB_LINK)]])
            )
    except: pass

    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not msg or msg.empty:
            return await message.reply_text("❌ الحلقة غير متوفرة في الأرشيف حالياً.")

        raw_cap = msg.caption or "مسلسل"
        title = re.sub(r'(الحلقة|حلقة|#|EP)?\s*\d+.*', '', raw_cap, flags=re.IGNORECASE).strip()
        ep_no = extract_ep(raw_cap)
        
        markup = await get_episodes_markup(v_id, title, ep_no)
        styled_title = " . ".join(list(title))
        cap = f"📺 <b>{styled_title}</b>\n🎞️ <b>الحلقة: {ep_no}</b>\n\n🍿 مشاهدة ممتعة!"
        
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=cap,
            reply_markup=markup
        )
        
        db_query("INSERT INTO videos (v_id, views) VALUES (%s, 1) ON CONFLICT (v_id) DO UPDATE SET views = videos.views + 1", (v_id,), fetch=False)

    except Exception as e:
        logging.error(f"Error: {e}")
        await message.reply_text("❌ حدث خطأ غير متوقع، جرب مجدداً.")

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, views INTEGER DEFAULT 0)", fetch=False)
    app.run()
