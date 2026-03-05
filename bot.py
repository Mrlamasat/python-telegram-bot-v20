import os
import psycopg2
import logging
import re
import difflib
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ForceReply
from pyrogram.enums import ParseMode

# ===== 1. الإعدادات الأساسية =====
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

# ===== 2. قاعدة البيانات =====
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

# ===== 3. أدوات المعالجة والتنظيف =====
def convert_ar_no(text):
    if not text: return ""
    arabic_numbers = '٠١٢٣٤٥٦٧٨٩'
    english_numbers = '0123456789'
    return text.translate(str.maketrans(arabic_numbers, english_numbers))

def normalize_text(text):
    if not text: return ""
    text = convert_ar_no(text).strip().lower()
    text = re.sub(r'^(مسلسل|فيلم|برنامج|عرض|انمي|حلقة|الحلقة)\s*', '', text)
    text = re.sub(r'[أإآ]', 'ا', text)
    text = text.replace('ة', 'ه').replace('ى', 'ي')
    text = re.sub(r'(.)\1+', r'\1', text)
    text = re.sub(r'[^a-zا-ي]', '', text) 
    return text

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔍 بحث آخر", callback_data="start_search"), InlineKeyboardButton("✍️ طلب مسلسل", callback_data="req_new")])
    return buttons

async def check_subscription(client, user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

MAIN_MENU = ReplyKeyboardMarkup([[KeyboardButton("🔍 كيف أبحث عن مسلسل؟")], [KeyboardButton("✍️ طلب مسلسل جديد")]], resize_keyboard=True)

# ===== 4. أوامر الإدارة والتنظيف =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.command("clear"))
async def clear_upload_state(client, message):
    db_query("DELETE FROM videos WHERE status != 'posted'", fetch=False)
    await message.reply_text("✅ تم تنظيف عمليات الرفع العالقة. يمكنك البدء من جديد الآن.")

@app.on_message(filters.private & filters.command("del") & filters.user(ADMIN_ID))
async def delete_episode(client, message):
    if len(message.command) < 3:
        return await message.reply_text("📝 الاستخدام: `/del [اسم المسلسل] [رقم الحلقة]`")
    title, ep = message.command[1], message.command[2]
    db_query("DELETE FROM videos WHERE title=%s AND ep_num=%s", (title, ep), fetch=False)
    await message.reply_text(f"🗑️ تم حذف {title} حلقة {ep} بنجاح.")

# ===== 5. محرك الرفع والنشر المطور =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = getattr(media, 'duration', 0) or 0
    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id, dur), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو.\nأرسل الآن **البوستر** واكتب اسم المسلسل في الوصف.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title = res[0][0], clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: {title}\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن **رقم الحلقة**:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats", "clear"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q = res[0]
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (message.text, v_id), fetch=False)
    b_info = await client.get_me()
    cap = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n<b>حلقة: [{message.text}]</b>\n<b>جودة: [{q}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")]])
    try:
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=cap, reply_markup=markup)
        await message.reply_text("🚀 تم النشر بنجاح.")
    except Exception as e:
        await message.reply_text(f"❌ خطأ نشر: {e}")

# ===== 6. معالجة البحث والطلبات =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats", "del"]))
async def advanced_search_handler(client, message):
    user_input = convert_ar_no(message.text)
    if user_input == "🔍 كيف أبحث عن مسلسل؟":
        return await message.reply_text("🔎 اكتب اسم المسلسل ورقم الحلقة (مثال: كلاي ١٥)")
    if user_input == "✍️ طلب مسلسل جديد":
        return await message.reply_text("📥 أرسل اسم المسلسل الذي تريده:", reply_markup=ForceReply(selective=True))

    query_norm = normalize_text(user_input)
    all_titles_res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    all_titles = [r[0] for r in all_titles_res] if all_titles_res else []
    matches = [t for t in all_titles if query_norm in normalize_text(t)]

    if matches:
        title = matches[0]
        first_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC LIMIT 1", (title,))
        if first_ep:
            bot_info = await client.get_me()
            btns = [[InlineKeyboardButton(f"🎬 {title}", url=f"https://t.me/{bot_info.username}?start={first_ep[0][0]}")]]
            await message.reply_text(f"🔍 نتائج البحث:", reply_markup=InlineKeyboardMarkup(btns))
    else:
        all_norm_map = {normalize_text(t): t for t in all_titles}
        close_matches = difflib.get_close_matches(query_norm, list(all_norm_map.keys()), n=1, cutoff=0.4)
        if close_matches:
            suggested = all_norm_map[close_matches[0]]
            markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ نعم، {suggested}", callback_data=f"conf_{close_matches[0]}"), InlineKeyboardButton("❌ لا، بلغ الإدارة", callback_data=f"rpt_{user_input[:20]}")]])
            return await message.reply_text(f"❓ هل تقصد: **{suggested}**؟", reply_markup=markup)
        await message.reply_text("❌ لم يتم العثور عليه، جرب كتابة الاسم بشكل أوضح.")

@app.on_callback_query(filters.regex("^conf_|^rpt_|^req_new|^start_search"))
async def callbacks_handler(client, cb):
    if cb.data.startswith("conf_"):
        q_norm = cb.data.replace("conf_", "")
        all_res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
        titles_map = {normalize_text(r[0]): r[0] for r in (all_res or [])}
        if q_norm in titles_map:
            title = titles_map[q_norm]
            first_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC LIMIT 1", (title,))
            if first_ep:
                v_id = first_ep[0][0]
                btns = await get_episodes_markup(title, v_id)
                await cb.message.delete()
                await client.copy_message(cb.message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"📺 {title}", reply_markup=InlineKeyboardMarkup(btns))
    elif cb.data.startswith("rpt_"):
        query_raw = cb.data.replace("rpt_", "")
        query_norm = normalize_text(query_raw)
        db_query("INSERT INTO requests (title_norm, title_raw, count) VALUES (%s, %s, 1) ON CONFLICT (title_norm) DO UPDATE SET count = requests.count + 1", (query_norm, query_raw), fetch=False)
        res_count = db_query("SELECT count FROM requests WHERE title_norm = %s", (query_norm,))
        total = res_count[0][0] if res_count else 1
        await client.send_message(ADMIN_ID, f"📢 طلب مفقود: {query_raw} ({total} طلب)")
        await cb.message.edit_text("✅ تم إبلاغ الإدارة.")
    elif cb.data == "req_new" or cb.data == "start_search":
        await cb.message.reply_text("🔎 اكتب اسم المسلسل:", reply_markup=ForceReply(selective=True))
    await cb.answer()

@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    top_v = db_query("SELECT title, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 5")
    top_r = db_query("SELECT title_raw, count FROM requests ORDER BY count DESC LIMIT 5")
    text = "📊 **الأكثر مشاهدة:**\n"
    for r in top_v or []: text += f"- {r[0]}: {r[1]} مشاهدة\n"
    text += "\n📌 **الأكثر طلباً:**\n"
    for r in top_r or []: text += f"- {r[0]}: {r[1]} طلب\n"
    await message.reply_text(text)

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا <b>{message.from_user.first_name}</b>!", reply_markup=MAIN_MENU)
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
    if not res: return
    title, ep = res[0]
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    btns = await get_episodes_markup(title, v_id)
    is_sub = await check_subscription(client, message.from_user.id)
    markup = InlineKeyboardMarkup(btns) if is_sub else InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]] + btns)
    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"<b>📺 {obfuscate_visual(title)} حلقة {ep}</b>", reply_markup=markup)

if __name__ == "__main__":
    app.run()
