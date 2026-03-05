import os
import psycopg2
import logging
import re
import difflib
from html import escape
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO)

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL").replace("postgresql://", "postgres://")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003554018307
FORCE_SUB_LINK = "https://t.me/+PyUeOtPN1fs0NDA0"
PUBLIC_POST_CHANNEL = "@ramadan2206"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Database Pool =====
db_pool = pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")

def db_query(query, params=(), fetch=True):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        conn.rollback()
        return None
    finally:
        db_pool.putconn(conn)

# ===== دوال التنظيف والتحويل الذكية =====
def convert_ar_no(text):
    arabic_numbers = "٠١٢٣٤٥٦٧٨٩"
    english_numbers = "0123456789"
    trans = str.maketrans(arabic_numbers, english_numbers)
    return text.translate(trans)

def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    # إزالة ال التعريف والهمزات والزخارف لتوحيد البحث
    text = re.sub(r'[أإآأ]', 'ا', text)
    text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ى', 'ي', text)
    text = re.sub(r'^(ال)', '', text)
    text = re.sub(r'\s+', '', text) # إزالة المسافات للبحث الملتصق
    return text

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

# ===== الدوال المساعدة =====
async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    buttons, row = [], []
    bot_info = await app.get_me()
    if res:
        for v_id, ep_num in res:
            label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}"))
            if len(row) == 5:
                buttons.append(row); row = []
        if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔍 بحث جديد", switch_inline_query_current_chat=""), InlineKeyboardButton("➕ طلب مسلسل", url="https://t.me/ramadan2206")])
    return buttons

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# ===== محرك البحث والتحليل الرقمي الذكي (النسخة الاحترافية المدمجة) =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def advanced_search_handler(client, message):
    raw_input = convert_ar_no(message.text)
    user_mention = message.from_user.mention

    if raw_input == "🔍 كيف أبحث عن مسلسل؟":
        return await message.reply_text("🔎 اكتب اسم المسلسل ورقم الحلقة مباشرة (مثال: كلاي ١٥) وسأجلبها لك فوراً!")

    if raw_input == "✍️ طلب مسلسل جديد" or (message.reply_to_message and "اسم المسلسل الذي تريده" in message.reply_to_message.text):
        if message.reply_to_message:
            await client.send_message(ADMIN_ID, f"🆕 **طلب مسلسل جديد:**\n👤 من: {user_mention}\n🎬 المسلسل: **{raw_input}**")
            return await message.reply_text("✅ تم إرسال طلبك للإدارة.")
        else:
            return await message.reply_text("📥 أرسل اسم المسلسل الذي تريده:", reply_markup=ForceReply(selective=True))

    ep_match = re.search(r'\d+', raw_input)
    target_ep = ep_match.group() if ep_match else None
    query_norm = normalize_text(re.sub(r'\d+', '', raw_input))
    
    if len(query_norm) < 2 and not target_ep: return

    all_titles_res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    if not all_titles_res: return await message.reply_text("❌ لا توجد مسلسلات حالياً.")
    all_titles = [r[0] for r in all_titles_res]
    
    matches = [t for t in all_titles if query_norm in normalize_text(t)]

    if matches:
        title = matches[0]
        if target_ep:
            video_res = db_query("SELECT v_id, quality, duration FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, target_ep))
            if video_res:
                v_id, q, dur = video_res[0]
                if not await check_subscription(client, message.from_user.id):
                    return await message.reply_text(f"⚠️ يجب الاشتراك لمشاهدة {title}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
                
                cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ حلقة : {target_ep}</b>"
                btns = await get_episodes_markup(title, v_id)
                return await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))

        btns = []
        for m in list(dict.fromkeys(matches))[:10]:
            first_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC LIMIT 1", (m,))
            if first_ep:
                btns.append([InlineKeyboardButton(f"🎬 {m}", url=f"https://t.me/{(await client.get_me()).username}?start={first_ep[0][0]}")])
        await message.reply_text(f"🔍 نتائج البحث عن '{message.text}':", reply_markup=InlineKeyboardMarkup(btns))
    
    else:
        normalized_map = {normalize_text(t): t for t in all_titles}
        close_matches = difflib.get_close_matches(query_norm, list(normalized_map.keys()), n=1, cutoff=0.5)
        if close_matches:
            suggested = normalized_map[close_matches[0]]
            return await message.reply_text(f"❓ هل تقصد: **{suggested}**؟", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ نعم", callback_data=f"search_{close_matches[0]}")]]))

        await client.send_message(ADMIN_ID, f"⚠️ **بحث فاشل:** {message.text} من {user_mention}")
        await message.reply_text("❌ لم يتم العثور على المسلسل.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ طلب مسلسل", callback_data="req_new")]]))

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"مرحباً بك يا محمد! أرسل اسم المسلسل للبحث..")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        title, ep, q, dur = res[0]
        btns = await get_episodes_markup(title, v_id)
        cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ حلقة : {ep}</b>"
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns))

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, poster_id TEXT, quality TEXT, ep_num TEXT, duration TEXT, status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0)", fetch=False)
    app.run()
