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

# ===== محرك المعالجة الذكي =====
def convert_ar_no(text):
    if not text: return ""
    arabic_numbers = '٠١٢٣٤٥٦٧٨٩'
    english_numbers = '0123456789'
    translation_table = str.maketrans(arabic_numbers, english_numbers)
    return text.translate(translation_table)

def normalize_text(text):
    if not text: return ""
    text = convert_ar_no(text).strip().lower()
    text = re.sub(r'^(مسلسل|مسلسلس|فيلم|برنامج|عرض|انمي|حلقة|الحلقة)\s*', '', text)
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
    buttons.append([
        InlineKeyboardButton("🔍 بحث عن مسلسل آخر", callback_data="start_search"), 
        InlineKeyboardButton("✍️ طلب مسلسل", callback_data="req_new")
    ])
    return buttons

async def check_subscription(client, user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

MAIN_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton("🔍 كيف أبحث عن مسلسل؟")], [KeyboardButton("✍️ طلب مسلسل جديد")]],
    resize_keyboard=True
)

# ===== 🛠️ محرك البحث والطلب المطور =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def advanced_search_handler(client, message):
    if not message.text: return # حماية من الرسائل الفارغة
    
    user_input = convert_ar_no(message.text)
    user_mention = message.from_user.mention if message.from_user else "مستخدم"

    if user_input == "🔍 كيف أبحث عن مسلسل؟":
        return await message.reply_text("🔎 اكتب اسم المسلسل ورقم الحلقة مباشرة (مثال: كلاي ١٥) وسأجلبها لك فوراً!")

    if user_input == "✍️ طلب مسلسل جديد":
        return await message.reply_text("📥 أرسل اسم المسلسل الذي تريده:", reply_markup=ForceReply(selective=True))

    is_request_reply = message.reply_to_message and "اسم المسلسل الذي تريده" in (message.reply_to_message.text or "")
    
    ep_match = re.search(r'\d+', user_input)
    target_ep = ep_match.group() if ep_match else None
    clean_query = re.sub(r'\d+', '', user_input).strip()
    query_norm = normalize_text(clean_query)
    
    if len(query_norm) < 2 and not target_ep: return

    all_titles_res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    all_titles = [r[0] for r in all_titles_res] if all_titles_res else []

    matches = [t for t in all_titles if query_norm in normalize_text(t)]

    if matches:
        title = matches[0]
        if is_request_reply:
            await message.reply_text(f"💡 هذا المسلسل موجود بالفعل لدينا! تفضل:")

        if target_ep:
            video_res = db_query("SELECT v_id, quality FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, target_ep))
            if video_res:
                v_id, q = video_res[0]
                db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (str(v_id),), fetch=False)
                if not await check_subscription(client, message.from_user.id):
                    cap = f"⚠️ **يجب الاشتراك لمشاهدة {title} حلقة {target_ep}**"
                    return await message.reply_text(cap, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
                
                cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ حلقة : {target_ep}</b>"
                btns = await get_episodes_markup(title, v_id)
                return await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))

        btns = []
        bot_info = await client.get_me()
        for m in list(dict.fromkeys(matches))[:10]:
            first_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC LIMIT 1", (m,))
            if first_ep:
                btns.append([InlineKeyboardButton(f"🎬 {m}", url=f"https://t.me/{bot_info.username}?start={first_ep[0][0]}")])
        await message.reply_text(f"🔍 نتائج البحث عن '{clean_query}':", reply_markup=InlineKeyboardMarkup(btns))
    
    else:
        if is_request_reply:
            # تخزين الطلب في جدول requests
            db_query("""
                INSERT INTO requests (title_norm, title_raw, count) 
                VALUES (%s, %s, 1) 
                ON CONFLICT (title_norm) 
                DO UPDATE SET count = requests.count + 1
            """, (query_norm, user_input), fetch=False)
            
            res_count = db_query("SELECT count FROM requests WHERE title_norm = %s", (query_norm,))
            r_count = res_count[0][0] if res_count else 1
            
            await client.send_message(ADMIN_ID, f"🆕 **طلب مسلسل جديد:**\n👤 من: {user_mention}\n🎬 المسلسل: **{user_input}**\n👥 إجمالي الطلبات: {r_count}")
            return await message.reply_text("✅ هذا المسلسل غير متوفر حالياً، تم إرسال طلبك للإدارة لتوفيره.")

        # نظام الاقتراحات
        all_norm_map = {normalize_text(t): t for t in all_titles}
        close_matches = difflib.get_close_matches(query_norm, list(all_norm_map.keys()), n=1, cutoff=0.4)
        if close_matches:
            suggested = all_norm_map[close_matches[0]]
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"✅ نعم، أقصد {suggested}", callback_data=f"conf_{close_matches[0]}")],
                [InlineKeyboardButton("❌ لا، بلغ الإدارة", callback_data=f"rpt_{query_norm[:15]}")]
            ])
            return await message.reply_text(f"❓ هل تقصد: **{suggested}**؟", reply_markup=markup)

        await client.send_message(ADMIN_ID, f"⚠️ **بحث فاشل:**\n👤 من: {user_mention}\n🔍 الكلمة: `{user_input}`")
        await message.reply_text("❌ لم يتم العثور على المسلسل. تم إبلاغ الإدارة لتوفيره.")

# ===== معالجة الأزرار والإحصائيات =====
@app.on_callback_query(filters.regex("^conf_|^rpt_|^req_new|^start_search"))
async def callbacks_handler(client, cb):
    if cb.data.startswith("conf_"):
        q_norm = cb.data.replace("conf_", "")
        all_titles_res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
        all_norm_titles = {normalize_text(t): t for r in (all_titles_res or []) for t in r}
        if q_norm in all_norm_titles:
            title = all_norm_titles[q_norm]
            first_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC LIMIT 1", (title,))
            if first_ep:
                bot_info = await client.get_me()
                btn = [[InlineKeyboardButton(f"🎬 {title}", url=f"https://t.me/{bot_info.username}?start={first_ep[0][0]}")]]
                await cb.message.edit_text(f"✅ نتيجة البحث عن **{title}**:", reply_markup=InlineKeyboardMarkup(btn))

    elif cb.data.startswith("rpt_"):
        query_val = cb.data.replace("rpt_", "")
        await client.send_message(ADMIN_ID, f"📢 **بلاغ بحث مفقود:**\n👤 المستخدم: {cb.from_user.mention}\n🔍 النص: `{query_val}`")
        await cb.message.edit_text("✅ تم تبليغ الإدارة بنجاح.")

    elif cb.data == "req_new":
        await cb.message.reply_text("📥 أرسل اسم المسلسل الذي تريده:", reply_markup=ForceReply(selective=True))
    
    elif cb.data == "start_search":
        await cb.message.reply_text("🔎 **اكتب الآن اسم المسلسل الذي تريد البحث عنه:**", reply_markup=ForceReply(selective=True))
    await cb.answer()

@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    top_v = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 5")
    top_r = db_query("SELECT title_raw, count FROM requests ORDER BY count DESC LIMIT 10")
    text = "📊 **إحصائيات البوت:**\n\n🔥 **الأكثر مشاهدة:**\n"
    for i, r in enumerate(top_v or [], 1): text += f"{i}. {r[0]} (ح {r[1]}) ← {r[2]} مشاهدة\n"
    text += "\n📌 **الأكثر طلباً (غير متوفر):**\n"
    for i, r in enumerate(top_r or [], 1): text += f"{i}. {r[0]} ← ({r[1]}) طلب\n"
    await message.reply_text(text)

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا <b>{message.from_user.first_name}</b>!", reply_markup=MAIN_MENU)
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if not res: return await message.reply_text("❌ عذراً، هذا الملف غير متوفر حالياً.")
    
    title, ep, q, dur = res[0]
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    
    btns = await get_episodes_markup(title, v_id)
    is_sub = await check_subscription(client, message.from_user.id)
    cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ حلقة : {ep}</b>\n<b>💿 جودة : {q}</b>"
    markup = InlineKeyboardMarkup(btns) if is_sub else InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]] + btns)
    
    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=markup)
    except Exception as e:
        await message.reply_text("❌ حدث خطأ في جلب الفيديو، قد يكون الملف محذوفاً من القناة المصدر.")

if __name__ == "__main__":
    app.run()
