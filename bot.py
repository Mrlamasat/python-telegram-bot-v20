import os
import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 7720165591
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== محرك البحث المباشر في المصدر =====

def extract_ep_number(text):
    if not text: return 0
    # بحث دقيق عن الأرقام لضمان عدم جلب 0
    match = re.search(r'(?:الحلقة|حلقة|EP|Episode|#)\s*(\d+)', text, re.IGNORECASE)
    if match: return int(match.group(1))
    # محاولة جلب أي رقم منفرد إذا فشل النمط أعلاه
    match_fallback = re.search(r'\b(\d+)\b', text)
    return int(match_fallback.group(1)) if match_fallback else 0

async def fetch_episodes_from_source(client, v_id):
    """جلب الحلقات مباشرة من القناة المصدر دون الحاجة لقاعدة بيانات"""
    try:
        v_id = int(v_id)
        # 1. تحديد البوستر (نبحث في 15 رسالة سابقة لضمان الدقة)
        poster_unique_id = None
        for i in range(1, 16):
            try:
                prev_msg = await client.get_messages(SOURCE_CHANNEL, v_id - i)
                if prev_msg and prev_msg.photo:
                    poster_unique_id = prev_msg.photo.file_unique_id
                    break
            except: continue
        
        if not poster_unique_id:
            return []

        # 2. مسح القناة (نطاق 150 رسالة حول الفيديو)
        found_episodes = []
        # نستخدم list comprehension لضمان صحة الأرقام
        search_ids = list(range(max(1, v_id - 100), v_id + 100))
        
        # جلب الرسائل كدفعة واحدة لتجنب الـ Flood
        messages = await client.get_messages(SOURCE_CHANNEL, search_ids)
        
        temp_poster = None
        for m in messages:
            if not m or m.empty: continue
            
            if m.photo:
                temp_poster = m.photo.file_unique_id
            elif (m.video or m.document) and temp_poster == poster_unique_id:
                ep_num = extract_ep_number(m.caption)
                if ep_num > 0:
                    found_episodes.append((ep_num, m.id))
        
        # ترتيب وتصفية (إزالة التكرار)
        found_episodes = sorted(list(set(found_episodes)), key=lambda x: x[0])
        return found_episodes
    except Exception as e:
        logging.error(f"Error in fetch_episodes: {e}")
        return []

# ===== بناء واجهة الأزرار =====

def build_markup(episodes, current_id):
    if not episodes: return None
    btns = []
    row = []
    for ep_num, m_id in episodes:
        label = f"✅ {ep_num}" if int(m_id) == int(current_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, callback_data=f"ep_{m_id}"))
        if len(row) == 5:
            btns.append(row)
            row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

# ===== المعالجات =====

@app.on_callback_query(filters.regex(r"^ep_"))
async def handle_callback(client, query):
    target_v_id = int(query.data.split("_")[1])
    # تحديث الأزرار والحلقة
    episodes = await fetch_episodes_from_source(client, target_v_id)
    markup = build_markup(episodes, target_v_id)
    
    msg = await client.get_messages(SOURCE_CHANNEL, target_v_id)
    # تجميل العنوان
    clean_name = re.sub(r'(الحلقة|حلقة)?\s*\d+.*', '', msg.caption or "مسلسل", flags=re.IGNORECASE).strip()
    pretty_title = " . ".join(list(clean_name[:25]))
    
    try:
        await query.message.delete()
        await client.copy_message(
            query.message.chat.id,
            SOURCE_CHANNEL,
            target_v_id,
            caption=f"📺 <b>{pretty_title}</b>\n🎞️ <b>الحلقة: {extract_ep_number(msg.caption)}</b>",
            reply_markup=markup
        )
    except:
        await query.answer("⚠️ الفيديو غير متاح حالياً")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply("أهلاً بك يا محمد في بوت الحلقات.")

    v_id = message.command[1]
    
    # فحص الاشتراك
    try:
        user = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        if user.status in ["left", "kicked"]:
            return await message.reply("❌ يجب الاشتراك أولاً لمشاهدة الحلقة", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
    except: pass

    # جلب مباشر
    episodes = await fetch_episodes_from_source(client, v_id)
    markup = build_markup(episodes, v_id)
    
    video_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
    clean_name = re.sub(r'(الحلقة|حلقة)?\s*\d+.*', '', video_msg.caption or "مسلسل", flags=re.IGNORECASE).strip()
    pretty_title = " . ".join(list(clean_name[:25]))

    await client.copy_message(
        message.chat.id,
        SOURCE_CHANNEL,
        int(v_id),
        caption=f"📺 <b>{pretty_title}</b>\n🎞️ <b>الحلقة: {extract_ep_number(video_msg.caption)}</b>",
        reply_markup=markup
    )

if __name__ == "__main__":
    app.run()
