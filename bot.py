import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from pyrogram.enums import ParseMode

# ===== الإعدادات الأساسية =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307  # القناة الصحيحة التي حددتها
FORCE_SUB_CHANNEL = -1003894735143     
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== تهيئة قاعدة البيانات =====
def init_database():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                v_id TEXT PRIMARY KEY,
                title TEXT,
                poster_id TEXT,
                quality TEXT,
                duration TEXT,
                ep_num TEXT,
                views INTEGER DEFAULT 0,
                status TEXT DEFAULT 'waiting',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close(); conn.close()
        return True
    except Exception as e:
        logging.error(f"❌ DB Init Error: {e}")
        return False

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
        logging.error(f"❌ DB Error: {e}")
        return None

# ===== الدوال المساعدة والبحث الذكي =====
def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'^(مسلسل|فيلم|برنامج|عرض)\s+', '', text)
    text = re.sub(r'[أإآ]', 'ا', text).replace('ة', 'ه').replace('ى', 'ي')
    text = re.sub(r'[^a-z0-9ا-ي]', '', text)
    return text

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text.replace(" ", "")))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

MAIN_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton("🔍 كيف أبحث عن مسلسل؟")], [KeyboardButton("✍️ طلب مسلسل جديد")]],
    resize_keyboard=True
)

# ===== 1. الإحصائيات =====
@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    res_total = db_query("SELECT COUNT(*), SUM(COALESCE(views, 0)) FROM videos WHERE status='posted'")
    res_top = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 5")
    t_eps = res_total[0][0] if res_total else 0
    t_views = res_total[0][1] if res_total and res_total[0][1] else 0
    text = f"📊 **إحصائيات المنصة:**\n\n📽️ الحلقات: `{t_eps}`\n👁️ المشاهدات: `{t_views}`\n\n🔥 **الأكثر مشاهدة:**\n"
    if res_top:
        for i, r in enumerate(res_top, 1):
            text += f"{i}. {r[0]} (ح {r[1]}) ← {r[2]} مشاهدة\n"
    await message.reply_text(text)

# ===== 2. نظام الرفع والنشر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    db_query("INSERT INTO videos (v_id, status, duration, created_at) VALUES (%s, 'waiting', %s, CURRENT_TIMESTAMP) ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id, dur), fetch=False)
    await message.reply_text("✅ استلمت الفيديو. أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY created_at DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = clean_series_title(message.caption or "مسلسل")
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
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY created_at DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (message.text, v_id), fetch=False)
    
    me = await client.get_me()
    cap = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n<b>الحلقة: [{message.text}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start=choose_{v_id}")]])
    try:
        # النشر في القناة الصحيحة مع التأكيد على نوع المعرف كـ Integer
        await client.send_photo(chat_id=int(PUBLIC_POST_CHANNEL), photo=p_id, caption=cap, reply_markup=markup)
        await message.reply_text("🚀 تم النشر بنجاح.")
    except Exception as e:
        await message.reply_text(f"❌ خطأ في النشر: {e}")

# ===== 3. البحث ونظام الحلقات التفاعلي =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def search_handler(client, message):
    if message.text == "🔍 كيف أبحث عن مسلسل؟":
        await message.reply_text("🔎 اكتب اسم المسلسل مباشرة.")
        return
    if message.text == "✍️ طلب مسلسل جديد":
        await message.reply_text("📥 أرسل اسم المسلسل وسنوفره لك.")
        return
    query = normalize_text(message.text)
    if len(query) < 2: return
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if query in normalize_text(t[0])]
    if matches:
        btns = [[InlineKeyboardButton(f"🎬 {m}", callback_data=f"lst_{m[:40]}")] for m in list(dict.fromkeys(matches))[:10]]
        await message.reply_text(f"🔍 نتائج البحث عن '{message.text}':", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await message.reply_text("❌ لم أجد نتائج.")

@app.on_callback_query(filters.regex("^lst_"))
async def list_eps_callback(client, cb):
    title_key = cb.data.replace("lst_", "")
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (f"{title_key}%",))
    if not res:
        await cb.answer("❌ لا توجد حلقات", show_alert=True); return
    btns, row = [], []
    for vid, ep in res:
        row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"get_{vid}"))
        if len(row) == 3: btns.append(row); row = []
    if row: btns.append(row)
    await cb.message.edit_text(f"📺 حلقات مسلسل: **{title_key}**", reply_markup=InlineKeyboardMarkup(btns))

@app.on_callback_query(filters.regex("^get_"))
async def get_video_callback(client, cb):
    v_id = cb.data.replace("get_", "")
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        t, ep, q, dur = res[0]
        if not await check_subscription(client, cb.from_user.id):
            await cb.answer("⚠️ يجب الاشتراك أولاً!", show_alert=True); return
        db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
        cap = f"<b>📺 المسلسل : {obfuscate_visual(t)}</b>\n<b>🎞️ حلقة : {ep}</b>\n<b>💿 جودة : {q}</b>\n<b>⏳ مدة : {dur}</b>"
        await client.copy_message(cb.message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap)
        await cb.answer("✅ تم الإرسال")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1].replace("choose_", "")
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res:
            t, ep, q, dur = res[0]
            if not await check_subscription(client, message.from_user.id):
                await message.reply_text("⚠️ اشترك أولاً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
                return
            db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
            cap = f"<b>📺 المسلسل : {obfuscate_visual(t)}</b>\n<b>🎞️ حلقة : {ep}</b>\n<b>💿 جودة : {q}</b>"
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap)
            return
    await message.reply_text(f"👋 أهلاً بك يا محمد في بوت المسلسلات.", reply_markup=MAIN_MENU)

if __name__ == "__main__":
    if init_database():
        app.run()
