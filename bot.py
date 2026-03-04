import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003554018307
FORCE_SUB_LINK = "https://t.me/+PyUeOtPN1fs0NDA0"
PUBLIC_POST_CHANNEL = "@ramadan2206"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== الدوال المساعدة =====
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

# --- دالة تنظيف البحث (إضافة ميزة البحث) ---
def clean_for_search(text):
    if not text: return ""
    text = text.replace(".", "").replace(" ", "")
    text = re.sub(r'[أإآ]', 'ا', text).replace('ة', 'ه').replace('ى', 'ي')
    return text.lower()

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅️ {ep_num}" if v_id == current_v_id else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    return buttons

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# ===== إرسال الفيديو النهائي =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    btns = await get_episodes_markup(title, v_id)
    is_subscribed = await check_subscription(client, user_id)
    
    safe_title = obfuscate_visual(escape(title))
    info_text = (
        f"<b><a href='https://s6.gifyu.com/images/S6atp.gif'>&#8205;</a>📺 المسلسل : {safe_title}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6at3.gif'>&#8205;</a>🎞️ رقم الحلقة : {escape(str(ep))}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6atZ.gif'>&#8205;</a>💿 الجودة : {escape(str(q))}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6at7.gif'>&#8205;</a>⏳ المدة : {escape(str(dur))}</b>"
    )
    cap = f"{info_text}\n\n🍿 <b>مشاهدة ممتعة نتمناها لكم!</b>"
    
    if not is_subscribed:
        cap += "\n\n⚠️ <b>انضم للقناة البديلة لمتابعة الحلقات القادمة 👇</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام (مهم)", url=FORCE_SUB_LINK)]] + (btns if btns else []))
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    try:
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, parse_mode=ParseMode.HTML, reply_markup=markup)
    except:
        await client.send_message(chat_id, f"🎬 {safe_title} - حلقة {ep}")

# ===== الأوامر والمعالجة =====
@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    top = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 10")
    text = "📊 <b>تقرير الأداء:</b>\n\n"
    for i, r in enumerate(top or [], 1):
        text += f"{i}. 🎬 {escape(r[0])} - ح {r[1]} ← {r[2]} مشاهدة\n"
    await message.reply_text(text, parse_mode=ParseMode.HTML)

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    d = media.duration if media and hasattr(media, 'duration') else 0
    dur = f"{d//3600:02}:{{(d%3600)//60:02}}:{{d%60:02}}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text(f"✅ تم المرفق. أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title = res[0][0], clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: <b>{escape(title)}</b>\nاختر الجودة:", reply_markup=markup, parse_mode=ParseMode.HTML)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: <b>{q}</b>. أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    b_info = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    caption = f"🎬 <b>{safe_t}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n<b>الجودة: [{q}]</b>\n<b>المدة: [{dur}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")]])
    
    await client.send_photo(PUBLIC_POST_CHANNEL, p_id, caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
    await message.reply_text("🚀 تم النشر في القناة العامة بنجاح.")

# --- قسم البحث المضاف (لا يؤثر على النشر) ---
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def search_handler(client, message):
    query = clean_for_search(message.text)
    if len(query) < 2: return
    
    all_titles = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (all_titles or []) if query in clean_for_search(t[0])]
    
    if matches:
        btns = []
        for m in matches[:10]:
            btns.append([InlineKeyboardButton(f"🎬 {m}", callback_data=f"res_{m[:40]}")])
        await message.reply_text(f"🔍 نتائج البحث عن '{message.text}':", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await message.reply_text("❌ لم أجد مسلسلاً بهذا الاسم.")

@app.on_callback_query(filters.regex("^res_"))
async def show_results(client, cb):
    title = cb.data.replace("res_", "")
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (f"{title}%",))
    if not res: return
    
    btns, row = [], []
    bot_info = await app.get_me()
    for vid, ep in res:
        row.append(InlineKeyboardButton(f"حلقة {ep}", url=f"https://t.me/{bot_info.username}?start={vid}"))
        if len(row) == 3: btns.append(row); row = []
    if row: btns.append(row)
    await cb.message.edit_text(f"📺 حلقات {title}:", reply_markup=InlineKeyboardMarkup(btns))

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>! اكتب اسم المسلسل للبحث.")
        return
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res: await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])

if __name__ == "__main__":
    app.run()
