import os
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

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅️ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    return buttons

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# ===== إرسال الفيديو النهائي للمستخدم =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    btns = await get_episodes_markup(title, v_id)
    is_subscribed = await check_subscription(client, user_id)
    
    safe_title = obfuscate_visual(escape(title))
    info_text = (
        f"<b>📺 المسلسل : {safe_title}</b>\n"
        f"<b>🎞️ رقم الحلقة : {escape(str(ep))}</b>\n"
        f"<b>💿 الجودة : {escape(str(q))}</b>\n"
        f"<b>⏳ المدة : {escape(str(dur))}</b>"
    )
    cap = f"{info_text}\n\n🍿 <b>مشاهدة ممتعة نتمناها لكم!</b>"

    final_btns = []
    if not is_subscribed:
        final_btns.append([InlineKeyboardButton("📥 انضمام (مهم)", url=FORCE_SUB_LINK)])
    
    if btns:
        final_btns.extend(btns)

    markup = InlineKeyboardMarkup(final_btns) if final_btns else None

    try:
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, parse_mode=ParseMode.HTML, reply_markup=markup)
    except Exception as e:
        logging.error(f"Copy Error: {e}")
        await client.send_message(chat_id, f"🎬 {safe_title} - حلقة {ep}")

# ===== استقبال الفيديو والبوستر =====
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
    
    bot_info = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    caption = f"🎬 <b>{safe_t}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n\nنتمنى لكم مشاهدة ممتعة."
    
    # التعديل هنا: رابط Start ببادرة choose_ لعرض الجودات لاحقاً
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{bot_info.username}?start=choose_{v_id}")]])
    
    try:
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
        await message.reply_text("🚀 تم النشر بزر (مشاهدة الحلقة) فقط.")
    except Exception as e:
        await message.reply_text(f"❌ خطأ في النشر: {e}")

# ===== معالجة اختيار الجودة داخل البوت =====
@app.on_callback_query(filters.regex("^get_vid_"))
async def get_video_by_quality(client, cb):
    v_id = cb.data.replace("get_vid_", "")
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        await send_video_final(client, cb.message.chat.id, cb.from_user.id, v_id, *res[0])
    await cb.answer()

# ===== أمر Start للمستخدمين =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>! ابحث عن مسلسلك المفضل.")
        return
    
    param = message.command[1]
    
    # إذا ضغط المستخدم على "مشاهدة الحلقة" من القناة
    if param.startswith("choose_"):
        ref_id = param.replace("choose_", "")
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (ref_id,))
        if res:
            title, ep = res[0]
            # جلب كل الجودات المتوفرة لنفس المسلسل ونفس الحلقة
            qualities = db_query("SELECT quality, v_id FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, ep))
            btns = [[InlineKeyboardButton(f"💿 جودة {q}", callback_data=f"get_vid_{vid}")] for q, vid in qualities]
            await message.reply_text(f"🎬 <b>{escape(title)} - حلقة {ep}</b>\n\nاختر الجودة التي تناسبك للمشاهدة:", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
    
    # إذا كان الرابط مباشراً لحلقة معينة
    else:
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (param,))
        if res: await send_video_final(client, message.chat.id, message.from_user.id, param, *res[0])

# ===== أمر الإحصائيات للأدمن =====
@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    top = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 10")
    text = "📊 <b>تقرير الأداء (الأكثر مشاهدة):</b>\n\n"
    if top:
        for i, r in enumerate(top, 1):
            text += f"{i}. 🎬 <b>{escape(r[0])}</b>\n└ حلقة {r[1]} ← 👤 <b>{r[2]} مشاهدة</b>\n\n"
    else: text += "لا توجد بيانات بعد."
    await message.reply_text(text, parse_mode=ParseMode.HTML)

if __name__ == "__main__":
    app.run()
