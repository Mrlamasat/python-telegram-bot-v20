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
    return " . ".join(list(text.replace(" ", "  ")))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

def clean_for_search(text):
    """تنظيف النص لمطابقة البحث بدون نقاط أو همزات"""
    if not text: return ""
    text = text.replace(".", "").replace(" ", "")
    text = re.sub(r'[أإآ]', 'ا', text).replace('ة', 'ه').replace('ى', 'ي')
    return text.lower()

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
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

# ===== إرسال الفيديو للمستخدم =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    btns = await get_episodes_markup(title, v_id)
    is_subscribed = await check_subscription(client, user_id)
    
    safe_title = obfuscate_visual(escape(title))
    cap = (
        f"<b>📺 المسلسل : {safe_title}</b>\n"
        f"<b>🎞️ رقم الحلقة : {escape(str(ep))}</b>\n"
        f"<b>💿 الجودة : {escape(str(q))}</b>\n"
        f"<b>⏳ المدة : {escape(str(dur))}</b>\n\n🍿 مشاهدة ممتعة!"
    )

    if not is_subscribed:
        cap += f"\n\n⚠️ <b>انضم للقناة لمتابعة الحلقات القادمة 👇</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]] + (btns if btns else []))
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, parse_mode=ParseMode.HTML, reply_markup=markup)

# ===== نظام النشر (المستقر كما هو) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') and media.duration else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text(f"✅ تم استلام الملف. أرسل البوستر الآن.")

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
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    me = await client.get_me()
    caption = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\nالحلقة: [{ep_num}]\nالجودة: [{q}]\nالمدة: [{dur}]"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
    await message.reply_text("🚀 تم النشر بنجاح.")

# ===== نظام البحث الجديد (مضاف بذكاء) =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def search_handler(client, message):
    user_query = clean_for_search(message.text)
    if len(user_query) < 2: return
    
    # جلب أسماء المسلسلات الفريدة
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if user_query in clean_for_search(t[0])]
    
    if matches:
        btns = [[InlineKeyboardButton(f"🎬 {m}", callback_data=f"sh_{m[:40]}")] for m in matches[:10]]
        await message.reply_text(f"🔍 نتائج البحث عن '{message.text}':", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await message.reply_text("❌ لم أجد مسلسلات بهذا الاسم.")

@app.on_callback_query(filters.regex("^sh_"))
async def show_eps(client, cb):
    title = cb.data.replace("sh_", "")
    # جلب الحلقات للمسلسل المختار
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (f"{title}%",))
    if not res: return
    
    btns, row = [], []
    for vid, ep in res:
        row.append(InlineKeyboardButton(f"حلقة {ep}", url=f"https://t.me/{(await client.get_me()).username}?start={vid}"))
        if len(row) == 3: btns.append(row); row = []
    if row: btns.append(row)
    
    await cb.message.edit_text(f"📺 حلقات مسلسل {title}:", reply_markup=InlineKeyboardMarkup(btns))

# ===== أوامر Start و Stats =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}! اكتب اسم المسلسل للبحث.")
        return
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res: await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])

@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    top = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 10")
    text = "📊 الأكثر مشاهدة:\n\n"
    for r in (top or []): text += f"🎬 {r[0]} (حلقة {r[1]}) ← {r[2]} مشاهدة\n"
    await message.reply_text(text)

if __name__ == "__main__":
    app.run()
