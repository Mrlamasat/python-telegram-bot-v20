دimport os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

# تعريف المتغير بشكل آمن
BOT_USERNAME = "YourBotUsername" 

# ===== وظائف مساعدة =====
def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ة]', 'ه', text)
    text = re.sub(r'[ى]', 'ي', text)
    text = re.sub(r'[ئؤ]', 'ء', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def clean_series_title(text):
    if not text: return "مسلسل"
    cleaned = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text)
    return cleaned.strip()

def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# جلب أزرار الحلقات
async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{BOT_USERNAME}?start={v_id}")
        row.append(btn)
        if len(row) == 5: buttons.append(row); row = []
    if row: buttons.append(row)
    return buttons

# تحديث يوزرنيم البوت عند التشغيل
@app.on_startup
async def startup_handler(client, _):
    global BOT_USERNAME
    try:
        me = await client.get_me()
        BOT_USERNAME = me.username
        print(f"✅ البوت انطلق باسم: @{BOT_USERNAME}")
    except Exception as e:
        logging.error(f"❌ خطأ في startup: {e}")

# ===== نظام البحث =====
@app.on_message(filters.private & ~filters.command(["start"]))
async def search_handler(client, message):
    user_query = message.text.strip()
    norm_query = normalize_text(user_query)
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if norm_query in normalize_text(t[0])]
    if not matches:
        await message.reply_text("🔍 لم أجد المسلسل، تم إرسال طلبك للإدارة.")
        return
    buttons = [[InlineKeyboardButton(f"🎬 {t}", callback_data=f"list_eps_{t[:30]}")] for t in matches[:10]]
    await message.reply_text("✨ نتائج البحث:", reply_markup=InlineKeyboardMarkup(buttons))

# ===== معالجة الأزرار =====
@app.on_callback_query(filters.regex("^list_eps_|^sel_q_|^get_vid_"))
async def cb_handler(client, cb):
    if cb.data.startswith("list_eps_"):
        title_part = cb.data.replace("list_eps_", "")
        res = db_query("SELECT DISTINCT ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY ep_num ASC", (f"{title_part}%",))
        buttons, row = [], []
        for (ep,) in res:
            row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"sel_q_{title_part}_{ep}"))
            if len(row) == 3: buttons.append(row); row = []
        if row: buttons.append(row)
        await cb.message.edit_text(f"📺 **اختر رقم الحلقة:**", reply_markup=InlineKeyboardMarkup(buttons))

    elif cb.data.startswith("sel_q_"):
        data = cb.data.replace("sel_q_", "").rsplit("_", 1)
        title_part, ep = data
        res = db_query("SELECT quality, v_id FROM videos WHERE title LIKE %s AND ep_num=%s AND status='posted'", (f"{title_part}%", ep))
        buttons = [[InlineKeyboardButton(f"💿 {q}", callback_data=f"get_vid_{v_id}")] for q, v_id in res]
        await cb.message.edit_text(f"🎬 **الحلقة {ep}** - اختر الجودة:", reply_markup=InlineKeyboardMarkup(buttons))

    elif cb.data.startswith("get_vid_"):
        v_id = cb.data.replace("get_vid_", "")
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s AND status='posted'", (v_id,))
        if res: await send_video_final(client, cb.message.chat.id, cb.from_user.id, v_id, *res[0])
        await cb.answer()

# ===== النشر والاستقبال =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    if not message.caption: return
    series_name = clean_series_title(message.caption)
    media = message.video or message.animation or message.document
    dur = f"{media.duration//3600:02d}:{(media.duration%3600)//60:02d}:{media.duration%60:02d}" if hasattr(media, 'duration') else "00:00:00"
    db_query("INSERT INTO videos (v_id, title, status, duration) VALUES (%s, %s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET title=%s, duration=%s", (v_id, series_name, dur, series_name, dur), fetch=False)
    await message.reply_text(f"✅ تم حفظ: {series_name}\nأرسل البوستر:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id, title FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    db_query("UPDATE videos SET poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (message.photo.file_id, res[0][0]), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(q, callback_data=f"q_{q}_{res[0][0]}") for q in ["4K", "HD", "SD"]]])
    await message.reply_text(f"📌 جودة مسلسل {res[0][1]}:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_", 2)
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل رقم الحلقة:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' LIMIT 1")
    if not res: return
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (message.text, res[0][0]), fetch=False)
    await publish_one_button(client, res[0][1], message.text, res[0][2], res[0][4])
    await message.reply_text("🚀 تم النشر بزر (مشاهدة الحلقة).")

async def publish_one_button(client, title, ep_num, p_id, dur):
    res = db_query("SELECT v_id FROM videos WHERE title=%s AND ep_num=%s LIMIT 1", (title, ep_num))
    v_id = res[0][0]
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{BOT_USERNAME}?start=choose_{v_id}")]])
    cap = f"🎬 <b>{title}</b>\n📌 الحلقة: {ep_num}\n⏳ المدة: {dur}\n\n🍿 اضغط للمشاهدة 👇"
    old = db_query("SELECT post_msg_id FROM videos WHERE title=%s AND ep_num=%s AND post_msg_id IS NOT NULL LIMIT 1", (title, ep_num))
    if old:
        try: return await client.edit_message_reply_markup(PUBLIC_POST_CHANNEL, int(old[0][0]), reply_markup=markup)
        except: pass
    msg = await client.send_photo(PUBLIC_POST_CHANNEL, p_id, caption=cap, reply_markup=markup)
    db_query("UPDATE videos SET post_msg_id=%s WHERE title=%s AND ep_num=%s", (msg.id, title, ep_num), fetch=False)

# الإرسال النهائي
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    ep_btns = await get_episodes_markup(title, v_id)
    cap = f"<b>📺 المسلسل : {title}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n<b>💿 الجودة : {q}</b>\n<b>⏳ المدة : {dur}</b>\n\n🍿 <b>مشاهدة ممتعة!</b>"
    final_btns = []
    try: await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
    except: final_btns.append([InlineKeyboardButton("📥 اشترك لمتابعة الجديد", url=FORCE_SUB_LINK)])
    if ep_btns: final_btns.extend(ep_btns)
    markup = InlineKeyboardMarkup(final_btns)
    try: await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=markup)
    except: pass

@app.on_message(filters.command("start") & filters.private)
async def start_h(client, message):
    if len(message.command) > 1:
        param = message.command[1]
        if param.startswith("choose_"):
            ref_id = param.replace("choose_", "")
            res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (ref_id,))
            if res:
                title, ep = res[0]
                qualities = db_query("SELECT quality, v_id FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, ep))
                btns = [[InlineKeyboardButton(f"💿 {q}", callback_data=f"get_vid_{vid}")] for q, vid in qualities]
                await message.reply_text(f"🎬 **{title} - حلقة {ep}**\nاختر الجودة المطلوبة:", reply_markup=InlineKeyboardMarkup(btns))
        else:
            res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s AND status='posted'", (param,))
            if res: await send_video_final(client, message.chat.id, message.from_user.id, param, *res[0])
    else:
        await message.reply_text("👋 ابحث عن مسلسلك المفضل الآن!")

if __name__ == "__main__":
    app.run()
