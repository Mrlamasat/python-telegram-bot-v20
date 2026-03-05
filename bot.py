import os
import psycopg2
import psycopg2.pool
import logging
import re
import asyncio
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
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== وظائف الاستخراج الذكي من المصدر =====
def extract_ep_number(text):
    if not text: return 0
    patterns = [
        r'(?:الحلقة|حلقة|EP|Episode)\s*[:#\-]?\s*(\d+)',
        r'#(\d+)',
        r'\b(\d+)\b'
    ]
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match: return int(match.group(1))
    return 0

async def fetch_episodes_from_source(client, v_id):
    """البحث في القناة مباشرة لجلب الحلقات المرتبطة بنفس البوستر"""
    v_id = int(v_id)
    poster_id = None
    
    # 1. البحث عن البوستر المرتبط بالفيديو (في آخر 10 رسائل)
    for i in range(1, 11):
        try:
            m = await client.get_messages(SOURCE_CHANNEL, v_id - i)
            if m and m.photo:
                poster_id = m.photo.file_unique_id
                start_search_from = m.id
                break
        except: continue
    
    if not poster_id:
        return []

    # 2. مسح القناة (نطاق 200 رسالة) لجلب كل الفيديوهات التي تتبع هذا البوستر
    found_episodes = [] # قائمة تحتوي على (رقم الحلقة، ID الرسالة)
    search_range = [i for i in range(v_id - 100, v_id + 100)]
    
    messages = await client.get_messages(SOURCE_CHANNEL, search_ids=search_range)
    
    current_poster = None
    for m in messages:
        if not m or m.empty: continue
        
        if m.photo:
            current_poster = m.photo.file_unique_id
        elif (m.video or m.document) and current_poster == poster_id:
            ep_num = extract_ep_number(m.caption)
            if ep_num > 0:
                found_episodes.append((ep_num, m.id))
    
    # ترتيب الحلقات حسب الرقم
    found_episodes.sort(key=lambda x: x[0])
    return found_episodes

# ===== بناء الأزرار =====
def build_markup(episodes, current_v_id):
    if not episodes: return None
    btns = []
    seen_eps = set()
    
    for ep_num, msg_id in episodes:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        
        label = f"✅ {ep_num}" if msg_id == int(current_v_id) else f"{ep_num}"
        btns.append(InlineKeyboardButton(label, callback_data=f"ep_{msg_id}"))
    
    # تقسيم 5 أزرار لكل صف
    rows = [btns[i:i + 5] for i in range(0, len(btns), 5)]
    return InlineKeyboardMarkup(rows)

# ===== المعالجات =====
@app.on_callback_query(filters.regex(r"^ep_"))
async def handle_callback(client, query):
    new_v_id = query.data.split("_")[1]
    
    # جلب الحلقات مباشرة من المصدر للعرض المحدث
    episodes = await fetch_episodes_from_source(client, int(new_v_id))
    markup = build_markup(episodes, new_v_id)
    
    msg = await client.get_messages(SOURCE_CHANNEL, int(new_v_id))
    title = " . ".join(list(re.sub(r'[^\w\s]', '', msg.caption or "مسلسل")[:20]))
    ep_num = extract_ep_number(msg.caption)

    try:
        await query.message.delete()
        await client.copy_message(
            query.message.chat.id, 
            SOURCE_CHANNEL, 
            int(new_v_id),
            caption=f"📺 <b>{title}</b>\n🎞️ <b>الحلقة: {ep_num}</b>",
            reply_markup=markup
        )
    except Exception as e:
        await query.answer("حدث خطأ أثناء جلب الحلقة")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply("أهلاً بك يا محمد في بوت الحلقات المباشر.")

    v_id = message.command[1]
    
    # فحص الاشتراك الإجباري
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        if member.status in ["left", "kicked"]:
            return await message.reply(
                "⚠️ اشترك أولاً لمشاهدة الحلقات:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)]])
            )
    except: pass

    # جلب البيانات مباشرة من القناة (المصدر)
    episodes = await fetch_episodes_from_source(client, v_id)
    markup = build_markup(episodes, v_id)
    
    video_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
    raw_title = re.sub(r'(الحلقة|حلقة)?\s*\d+.*', '', video_msg.caption or "مسلسل", flags=re.IGNORECASE).strip()
    title = " . ".join(list(raw_title[:25]))
    ep_num = extract_ep_number(video_msg.caption)

    await client.copy_message(
        message.chat.id, 
        SOURCE_CHANNEL, 
        int(v_id),
        caption=f"📺 <b>{title}</b>\n🎞️ <b>الحلقة: {ep_num}</b>",
        reply_markup=markup
    )

if __name__ == "__main__":
    print("🚀 البوت يعمل الآن بنظام الجلب المباشر من المصدر...")
    app.run()
