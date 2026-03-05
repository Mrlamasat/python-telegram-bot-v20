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
    # تم تعديل الترتيب ليكون رقمي صحيح CAST لضمان ترتيب 1, 2, 10 وليس 1, 10, 2
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
    if user_id == ADMIN_ID: return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# ===== إرسال الفيديو النهائي للمستخدم =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    # تحديث البيانات من السورس قبل الإرسال (لتحقيق طلبك بالتعديل التلقائي)
    try:
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if source_msg and source_msg.caption:
            title = clean_series_title(source_msg.caption)
            ep_match = re.search(r'(\d+)', source_msg.caption)
            if ep_match: ep = int(ep_match.group(1))
            # تحديث القاعدة بالبيانات الجديدة من السورس
            db_query("UPDATE videos SET title=%s, ep_num=%s WHERE v_id=%s", (title, ep, v_id), fetch=False)
    except: pass

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

    if not is_subscribed:
        cap += f"\n\n⚠️ <b>انضم للقناة لمتابعة الحلقات القادمة 👇</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام (مهم)", url=FORCE_SUB_LINK)]] + (btns if btns else []))
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    try:
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, parse_mode=ParseMode.HTML, reply_markup=markup)
    except:
        await client.send_message(chat_id, f"🎬 {safe_title} - حلقة {ep}")

# ===== [إضافة] أوامر الإدارة الجديدة =====

@app.on_message(filters.command("clear") & (filters.user(ADMIN_ID) | filters.chat(SOURCE_CHANNEL)))
async def clear_handler(client, message):
    db_query("DELETE FROM videos WHERE status != 'posted'", fetch=False)
    await message.reply_text("✅ تم تنظيف عمليات الرفع غير المكتملة.")

@app.on_message(filters.command("del") & filters.user(ADMIN_ID))
async def delete_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text("📝 ارسل: `/del اسم_المسلسل رقم_الحلقة` للحذف.")
    
    # محاولة استخراج الاسم والرقم
    full_text = message.text.replace("/del ", "")
    ep_num = re.search(r'(\d+)$', full_text)
    if ep_num:
        ep = ep_num.group(1)
        title = full_text.replace(ep, "").strip()
        db_query("DELETE FROM videos WHERE title = %s AND ep_num = %s", (title, int(ep)), fetch=False)
        await message.reply_text(f"🗑️ تم حذف مسلسل {title} حلقة {ep} بنجاح.")
    else:
        await message.reply_text("❌ لم استطع تحديد رقم الحلقة.")

# ===== بقية كودك الأصلي كما هو بدون تغيير =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    d = media.duration if media and hasattr(media, 'duration') else 0
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

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats", "del", "clear"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    b_info = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    caption = f"🎬 <b>{safe_t}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n<b>الجودة: [{q}]</b>\n<b>المدة: [{dur}]</b>\n\nنتمنى لكم مشاهدة ممتعة."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")]])
    
    try:
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
        await message.reply_text("🚀 تم النشر في القناة الخاصة بنجاح.")
    except Exception as e:
        await message.reply_text(f"❌ فشل النشر.\nالخطأ: {e}")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>!")
        return
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res: await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])

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
