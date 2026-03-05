import os
import psycopg2
import logging
import re
import difflib
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ForceReply
from pyrogram.enums import ParseMode

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
        if fetch: result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close(); conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== الدوال المساعدة وتحويل الأرقام =====
def convert_ar_no(text):
    arabic_numbers = '٠١٢٣٤٥٦٧٨٩'
    english_numbers = '0123456789'
    translation_table = str.maketrans(arabic_numbers, english_numbers)
    return text.translate(translation_table)

def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'^(مسلسل|فيلم|برنامج|عرض|انمي|مسلسلس)\s*', '', text)
    text = re.sub(r'[أإآ]', 'ا', text).replace('ة', 'ه').replace('ى', 'ي')
    text = re.sub(r'(.)\1+', r'\1', text) 
    return text

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

# أزرار البحث الدائم
EXTRA_BUTTONS = [
    [InlineKeyboardButton("🔍 بحث عن مسلسل آخر", switch_inline_query_current_chat=""),
     InlineKeyboardButton("✍️ طلب مسلسل", callback_data="req_new")]
]

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    if res:
        for v_id, ep_num in res:
            if ep_num in seen_eps: continue
            seen_eps.add(ep_num)
            label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
            btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
            row.append(btn)
            if len(row) == 5:
                buttons.append(row); row = []
        if row: buttons.append(row)
    buttons.extend(EXTRA_BUTTONS)
    return buttons

async def check_subscription(client, user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# ===== معالجة التعديل والنشر والرفع ===== (بقية الدوال الأساسية)
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.photo | filters.document))
async def handle_edit_source(client, message):
    v_id = str(message.id)
    new_caption = message.caption if message.caption else ""
    if not new_caption: return
    new_title = clean_series_title(new_caption)
    res = db_query("SELECT ep_num, quality, duration, public_msg_id FROM videos WHERE v_id=%s", (v_id,))
    if not res: return
    ep_num, q, dur, public_msg_id = res[0]
    db_query("UPDATE videos SET title=%s WHERE v_id=%s", (new_title, v_id), fetch=False)
    if public_msg_id:
        b_info = await client.get_me()
        new_cap = f"🎬 <b>{obfuscate_visual(escape(new_title))}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n<b>الجودة: [{q}]</b>\n<b>المدة: [{dur}]</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")]])
        try: await client.edit_message_caption(chat_id=PUBLIC_POST_CHANNEL, message_id=public_msg_id, caption=new_cap, reply_markup=markup)
        except: pass

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    d = media.duration if media and hasattr(media, 'duration') else 0
    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو. أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res or not message.caption:
        await message.reply_text("❌ ارفع الفيديو أولاً ثم البوستر مع العنوان.")
        return
    v_id, title = res[0][0], clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: {escape(title)}\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = int(message.text)
    b_info = await client.get_me()
    caption = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n<b>الجودة: [{q}]</b>\n<b>المدة: [{dur}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")]])
    try:
        sent_msg = await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
        db_query("UPDATE videos SET ep_num=%s, status='posted', public_msg_id=%s WHERE v_id=%s", (ep_num, sent_msg.id, v_id), fetch=False)
        await message.reply_text("🚀 تم النشر بنجاح.")
    except Exception as e: await message.reply_text(f"❌ خطأ: {e}")

# ===== معالج البحث الذكي المطور (الذي طلبته) =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def advanced_smart_search(client, message):
    user_input = convert_ar_no(message.text)
    user_mention = message.from_user.mention
    
    # الرد على الأزرار الثابتة
    if user_input == "🔍 كيف أبحث عن مسلسل؟":
        return await message.reply_text("🔎 اكتب اسم المسلسل مباشرة (مثال: كلاي) أو المسلسل مع الحلقة (مثال: كلاي 15).")
    
    if user_input == "✍️ طلب مسلسل جديد" or (message.reply_to_message and "أرسل اسم المسلسل" in message.reply_to_message.text):
        if message.reply_to_message:
            await client.send_message(ADMIN_ID, f"🆕 **طلب مسلسل:**\n👤 {user_mention}\n🎬 {user_input}")
            await message.reply_text("✅ تم إرسال طلبك للإدارة.")
        else:
            await message.reply_text("📥 أرسل اسم المسلسل الذي تريده الآن:", reply_markup=ForceReply(selective=True))
        return

    # استخراج رقم الحلقة واسم المسلسل
    ep_match = re.search(r'\d+', user_input)
    target_ep = ep_match.group() if ep_match else None
    clean_query = re.sub(r'\d+', '', user_input)
    query = normalize_text(clean_query)
    
    if len(query) < 2 and not target_ep: return

    all_titles_res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    if not all_titles_res: return await message.reply_text("📭 لا توجد مسلسلات حالياً.")
    
    all_titles = [r[0] for r in all_titles_res]
    normalized_map = {normalize_text(t): t for t in all_titles}

    matches = [raw for norm, raw in normalized_map.items() if query in norm]

    if matches:
        title = matches[0]
        if target_ep:
            video_res = db_query("SELECT v_id, quality, duration FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, target_ep))
            if video_res:
                v_id, q, dur = video_res[0]
                db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
                if not await check_subscription(client, message.from_user.id):
                    return await message.reply_text(f"⚠️ **يجب الاشتراك لمشاهدة {title} حلقة {target_ep}**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)]]))
                
                cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ حلقة : {target_ep}</b>\n<b>💿 جودة : {q}</b>"
                btns = await get_episodes_markup(title, v_id)
                return await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))

        bot_info = await client.get_me()
        btns = []
        for m in list(dict.fromkeys(matches))[:10]:
            first_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC LIMIT 1", (m,))
            if first_ep: btns.append([InlineKeyboardButton(f"🎬 {m}", url=f"https://t.me/{bot_info.username}?start={first_ep[0][0]}")])
        await message.reply_text(f"🔍 نتائج البحث عن '{user_input}':", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await client.send_message(ADMIN_ID, f"⚠️ **بحث فاشل:**\n👤 {user_mention}\n🔍 `{user_input}`")
        await message.reply_text("❌ لم أجد المسلسل، تم إبلاغ الإدارة لنوفرة لك.")

# ===== معالج الـ Start =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"مرحباً بك يا <b>{escape(message.from_user.first_name)}</b>!", reply_markup=MAIN_MENU)
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if not res: return
    title, ep, q, dur = res[0]
    db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    btns = await get_episodes_markup(title, v_id)
    is_sub = await check_subscription(client, message.from_user.id)
    cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ حلقة : {ep}</b>\n<b>💿 جودة : {q}</b>\n<b>⏳ مدة : {dur}</b>"
    markup = InlineKeyboardMarkup(btns) if is_sub else InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)]] + btns)
    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=markup)
    except: await message.reply_text(f"🎬 {title} - حلقة {ep}")

@app.on_callback_query(filters.regex("req_new"))
async def req_callback(client, cb):
    await cb.message.reply_text("📥 أرسل اسم المسلسل الذي تريده الآن:", reply_markup=ForceReply(selective=True))
    await cb.answer()

MAIN_MENU = ReplyKeyboardMarkup([[KeyboardButton("🔍 كيف أبحث عن مسلسل؟")], [KeyboardButton("✍️ طلب مسلسل جديد")]], resize_keyboard=True)

if __name__ == "__main__":
    app.run()
