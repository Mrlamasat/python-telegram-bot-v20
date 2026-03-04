import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from pyrogram.enums import ParseMode

# ===== الإعدادات الأساسية (المتغيرات البيئية) =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

# ===== IDs القنوات =====
SOURCE_CHANNEL = -1003547072209        # قناة الاستقبال
PUBLIC_POST_CHANNEL = -1003554018307   # قناة النشر
FORCE_SUB_CHANNEL = -1003894735143     # قناة الاشتراك
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
        logging.error(f"❌ خطأ في قاعدة البيانات: {e}")
        return None

# ===== الدالة المطورة: البحث الذكي وتوحيد النصوص =====
def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    
    # 1. إزالة الكلمات التعريفية الزائدة (حل مشكلة "مسلسل مولانا")
    text = re.sub(r'^(مسلسل|فيلم|برنامج|كرتون|انمي|افلام|مسلسلات)\s+', '', text)
    
    # 2. توحيد الأحرف العربية الصعبة
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ة]', 'ه', text)
    text = re.sub(r'[ى]', 'ي', text)
    text = re.sub(r'[ئؤ]', 'ء', text)
    
    # 3. تنظيف المسافات
    text = re.sub(r'\s+', ' ', text).strip()
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
    except: 
        return False

# القائمة الثابتة بالأسفل
MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔍 كيف أبحث عن مسلسل؟")],
        [KeyboardButton("✍️ طلب مسلسل جديد")]
    ],
    resize_keyboard=True
)

# ===== إرسال الفيديو النهائي وتثبيت القائمة السفلية =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    buttons, row, seen_eps = [], [], set()
    me = await client.get_me()
    
    for vid, ep_num in (res or []):
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅ {ep_num}" if str(vid) == str(v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
        if len(row) == 5: 
            buttons.append(row); row = []
    if row: buttons.append(row)

    is_subscribed = await check_subscription(client, user_id)
    final_btns = []
    if not is_subscribed:
        final_btns.append([InlineKeyboardButton("📥 اشترك لمتابعة الحلقات", url=FORCE_SUB_LINK)])
    if buttons: final_btns.extend(buttons)

    cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n<b>💿 الجودة : {q}</b>\n<b>⏳ المدة : {dur}</b>"
    
    try:
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, 
                                 reply_markup=InlineKeyboardMarkup(final_btns) if final_btns else None)
        await client.send_message(chat_id, "🔍 ابحث عن أي مسلسل آخر بكتابة اسمه هنا 👇", reply_markup=MAIN_MENU)
    except:
        await client.send_message(chat_id, f"🎬 {title} - حلقة {ep}", reply_markup=MAIN_MENU)

# ===== معالجة الرسائل والبحث الذكي =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def message_handler(client, message):
    if message.from_user.is_bot: return 
    user_id = message.from_user.id
    text = message.text

    if text == "🔍 كيف أبحث عن مسلسل؟":
        await message.reply_text("🔎 **طريقة البحث:** اكتب اسم المسلسل مباشرة (مثلاً: قيامة عثمان).\nسيقوم البوت بتجاهل كلمات مثل 'مسلسل' أو 'فيلم' والبحث عن الاسم مباشرة!")
        return
    if text == "✍️ طلب مسلسل جديد":
        await message.reply_text("📥 أرسل اسم المسلسل وسأبلغ الإدارة فوراً.")
        return

    if not await check_subscription(client, user_id):
        await message.reply_text("⚠️ اشترك أولاً لتفعيل البحث:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 اشترك الآن", url=FORCE_SUB_LINK)]]))
        return

    # استخدام الدالة المطورة لمعالجة نص البحث
    norm_query = normalize_text(text)
    if not norm_query or len(norm_query) < 2: return

    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted' ORDER BY title ASC")
    matches = [row[0] for row in (res or []) if norm_query in normalize_text(row[0])]
    
    if matches:
        matches = list(dict.fromkeys(matches))[:10]
        buttons = [[InlineKeyboardButton(f"🎬 {t}", callback_data=f"lst_{t[:40]}")] for t in matches]
        await message.reply_text(f"🔍 نتائج البحث عن '{text}':", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message.reply_text(f"❌ لم أجد '{text}'. تم إرسال طلبك للإدارة.")
        try: await client.send_message(ADMIN_ID, f"📥 طلب جديد: {text}")
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
                qualities = db_query("SELECT DISTINCT quality, v_id FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, ep))
                btns = [[InlineKeyboardButton(f"💿 {q}", callback_data=f"get_vid_{vid}")] for q, vid in qualities]
                await message.reply_text(f"🎬 **{escape(title)} - حلقة {ep}**\n\nاختر الجودة المطلوبة 👇:", 
                                         reply_markup=MAIN_MENU) 
                await message.reply_text("👇", reply_markup=InlineKeyboardMarkup(btns))
        else:
            res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (param,))
            if res: await send_video_final(client, message.chat.id, message.from_user.id, param, *res[0])
    else:
        await message.reply_text(f"👋 أهلاً بك يا {message.from_user.first_name}.\nاستخدم القائمة بالأسفل للبحث أو الطلب.", reply_markup=MAIN_MENU)

# (بقية دوال Callback ورفع المرفقات تبقى كما هي في الكود السابق لضمان استقرار العمل)
@app.on_callback_query(filters.regex("^lst_|^sqs_|^get_vid_|^q_"))
async def cb_handler(client, cb):
    if cb.data.startswith("lst_"):
        t_part = cb.data.replace("lst_", "")
        res = db_query("SELECT DISTINCT ep_num FROM videos WHERE title = %s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (t_part,))
        buttons, row = [], []
        for (ep,) in (res or []):
            v_res = db_query("SELECT v_id FROM videos WHERE title = %s AND ep_num = %s LIMIT 1", (t_part, ep))
            if v_res:
                row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"sqs_{v_res[0][0]}"))
                if len(row) == 3: buttons.append(row); row = []
        if row: buttons.append(row)
        await cb.message.edit_text(f"📺 **{t_part}**\nاختر الحلقة:", reply_markup=InlineKeyboardMarkup(buttons))
    elif cb.data.startswith("sqs_"):
        v_id = cb.data.replace("sqs_", "")
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
        if res:
            title, ep = res[0]
            qualities = db_query("SELECT DISTINCT quality, v_id FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, ep))
            btns = [[InlineKeyboardButton(f"💿 {q}", callback_data=f"get_vid_{vid}")] for q, vid in qualities]
            await cb.message.edit_text(f"🎬 {title} - حلقة {ep}\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(btns))
    elif cb.data.startswith("get_vid_"):
        v_id = cb.data.replace("get_vid_", "")
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res: await send_video_final(client, cb.message.chat.id, cb.from_user.id, v_id, *res[0])
        await cb.answer()
    elif cb.data.startswith("q_"):
        parts = cb.data.split("_"); q, v_id = parts[1], parts[2]
        db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
        await cb.message.edit_text(f"✅ الجودة: {q}\nأرسل الآن رقم الحلقة لرفعها:")

# ===== استقبال الرفع (سورس) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text(f"✅ تم استقبال المرفق ({dur}). أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]; title = clean_series_title(message.caption or "مسلسل")
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: {title}\nاختر الجودة المطلوبة:", reply_markup=markup)

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (message.text, v_id), fetch=False)
    me = await client.get_me()
    caption = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n<b>الحلقة: [{message.text}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start=choose_{v_id}")]])
    await client.send_photo(PUBLIC_POST_CHANNEL, p_id, caption=caption, reply_markup=markup)
    await message.reply_text("🚀 تم النشر بنجاح في القناة العامة.")

if __name__ == "__main__":
    app.run()
