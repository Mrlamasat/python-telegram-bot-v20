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
def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ة]', 'ه', text)
    text = re.sub(r'[ى]', 'ي', text)
    text = re.sub(r'[ئؤ]', 'ء', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# القائمة الثابتة أسفل الشاشة
MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔍 كيف أبحث عن مسلسل؟")],
        [KeyboardButton("📋 قائمة المسلسلات"), KeyboardButton("✍️ طلب مسلسل جديد")]
    ],
    resize_keyboard=True
)

# ===== إرسال الفيديو النهائي =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    
    # جلب الحلقات
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    buttons, row, seen_eps = [], [], set()
    me = await client.get_me()
    for vid, ep_num in (res or []):
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅ {ep_num}" if str(vid) == str(v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
        if len(row) == 5: buttons.append(row); row = []
    if row: buttons.append(row)

    is_subscribed = await check_subscription(client, user_id)
    final_btns = []
    if not is_subscribed:
        final_btns.append([InlineKeyboardButton("📥 اشترك لمتابعة الحلقات", url=FORCE_SUB_LINK)])
    if buttons: final_btns.extend(buttons)

    cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n<b>💿 الجودة : {q}</b>\n<b>⏳ المدة : {dur}</b>\n\n🍿 <b>مشاهدة ممتعة!</b>"

    try:
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(final_btns) if final_btns else None)
    except:
        await client.send_message(chat_id, f"🎬 {title} - حلقة {ep}")

# ===== معالجة الرسائل النصية والبحث =====
@app.on_message(filters.private & ~filters.command(["start", "stats"]))
async def message_handler(client, message):
    user_id = message.from_user.id
    text = message.text

    # شرح ميزة البحث
    if text == "🔍 كيف أبحث عن مسلسل؟":
        await message.reply_text(
            "🔎 **طريقة البحث الذكي:**\n\n"
            "فقط اكتب اسم المسلسل (مثلاً: قيامة عثمان) وأرسله هنا مباشرة.\n"
            "سأقوم بعرض النتائج المطابقة فوراً.\n\n"
            "✅ **نصيحة:** اكتب الكلمات الأساسية من اسم المسلسل لنتائج أدق.",
            reply_markup=MAIN_MENU
        )
        return

    # طلب مسلسل
    if text == "✍️ طلب مسلسل جديد":
        await message.reply_text("📥 **أرسل اسم المسلسل الذي تطلبه الآن وسيتم إبلاغ الإدارة فوراً.**")
        return

    # تنفيذ البحث الفعلي
    if not await check_subscription(client, user_id):
        await message.reply_text("⚠️ اشتراك أولاً لتفعيل البحث:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 اشترك الآن", url=FORCE_SUB_LINK)]]))
        return

    norm_query = normalize_text(text)
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if norm_query in normalize_text(t[0])]
    
    if matches:
        buttons = [[InlineKeyboardButton(f"🎬 {t}", callback_data=f"lst_{t[:30]}")] for t in matches[:10]]
        await message.reply_text(f"🔍 **نتائج البحث عن '{text}':**", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message.reply_text(f"❌ لم أجد '{text}' في المكتبة.\n✅ تم إرسال طلبك للإدارة.")
        try: await client.send_message(ADMIN_ID, f"📥 طلب جديد من {message.from_user.mention}: {text}")
        except: pass

# ===== أمر Start =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        param = message.command[1]
        if param.startswith("choose_"):
            ref_id = param.replace("choose_", "")
            res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (ref_id,))
            if res:
                title, ep = res[0]
                qualities = db_query("SELECT quality, v_id FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, ep))
                btns = [[InlineKeyboardButton(f"💿 جودة {q}", callback_data=f"get_vid_{vid}")] for q, vid in qualities]
                await message.reply_text(f"🎬 **{escape(title)} - حلقة {ep}**\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(btns))
        else:
            res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (param,))
            if res: await send_video_final(client, message.chat.id, message.from_user.id, param, *res[0])
    else:
        await message.reply_text(
            f"👋 أهلاً بك يا {message.from_user.first_name} في بوت المسلسلات.\n\nاستخدم الأزرار أسفل الشاشة لمعرفة طريقة البحث أو طلب مسلسل جديد.",
            reply_markup=MAIN_MENU
        )

# (بقية الدوال: callback_query, receive_video, receive_poster, receive_ep_num تظل كما هي في النسخة السابقة)
@app.on_callback_query(filters.regex("^lst_|^sqs_|^get_vid_|^q_"))
async def cb_handler(client, cb):
    if cb.data.startswith("lst_"):
        t_part = cb.data.replace("lst_", "")
        res = db_query("SELECT DISTINCT ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY ep_num ASC", (f"%{t_part}%",))
        buttons, row = [], []
        for (ep,) in res:
            v_res = db_query("SELECT v_id FROM videos WHERE title LIKE %s AND ep_num=%s LIMIT 1", (f"%{t_part}%", ep))
            if v_res:
                row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"sqs_{v_res[0][0]}"))
                if len(row) == 3: buttons.append(row); row = []
        if row: buttons.append(row)
        await cb.message.edit_text("📺 **اختر رقم الحلقة:**", reply_markup=InlineKeyboardMarkup(buttons))
    elif cb.data.startswith("sqs_"):
        v_id = cb.data.replace("sqs_", "")
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
        if res:
            title, ep = res[0]
            qualities = db_query("SELECT quality, v_id FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, ep))
            btns = [[InlineKeyboardButton(f"💿 جودة {q}", callback_data=f"get_vid_{vid}")] for q, vid in qualities]
            await cb.message.edit_text(f"🎬 **{title} - حلقة {ep}**\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(btns))
    elif cb.data.startswith("get_vid_"):
        v_id = cb.data.replace("get_vid_", "")
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res: await send_video_final(client, cb.message.chat.id, cb.from_user.id, v_id, *res[0])
        await cb.answer()
    elif cb.data.startswith("q_"):
        _, q, v_id = cb.data.split("_")
        db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
        await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') else 0
    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text(f"✅ تم المرفق ({dur}). أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title = res[0][0], clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: {title}\nاختر الجودة:", reply_markup=markup)

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (message.text, v_id), fetch=False)
    me = await client.get_me()
    caption = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n<b>الحلقة: [{message.text}]</b>\n\nنتمنى لكم مشاهدة ممتعة."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start=choose_{v_id}")]])
    await client.send_photo(PUBLIC_POST_CHANNEL, p_id, caption=caption, reply_markup=markup)
    await message.reply_text("🚀 نُشرت بنجاح.")

@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    top = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 10")
    text = "📊 الأكثر مشاهدة:\n\n"
    if top:
        for i, r in enumerate(top, 1): text += f"{i}. {r[0]} ({r[1]}) -> {r[2]} مشاهدة\n"
    await message.reply_text(text)

if __name__ == "__main__":
    app.run()
