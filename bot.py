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

async def notify_admin(content, report_type="alert"):
    prefix = "⚠️ **بلاغ عطل**" if report_type == "alert" else "📝 **طلب جديد**"
    try: await app.send_message(ADMIN_ID, f"{prefix}\n\n{content}")
    except: pass

# ===== نظام البحث =====
@app.on_message(filters.private & ~filters.command(["start"]))
async def search_handler(client, message):
    user_query = message.text.strip()
    norm_query = normalize_text(user_query)
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if norm_query in normalize_text(t[0])]
    
    if not matches:
        await message.reply_text("🔍 لم أجد المسلسل، تم إرسال طلبك للإدارة.")
        await notify_admin(f"👤 {message.from_user.mention} بحث عن: `{user_query}`", "request")
        return

    buttons = [[InlineKeyboardButton(f"🎬 {t}", callback_data=f"list_eps_{t[:30]}")] for t in matches[:10]]
    await message.reply_text("✨ نتائج البحث:", reply_markup=InlineKeyboardMarkup(buttons))

# ===== معالجة الحلقات والجودات =====
@app.on_callback_query(filters.regex("^list_eps_|^sel_q_|^get_vid_"))
async def cb_handler(client, cb):
    if cb.data.startswith("list_eps_"):
        title_part = cb.data.replace("list_eps_", "")
        res = db_query("SELECT DISTINCT ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY ep_num ASC", (f"{title_part}%",))
        if not res: return await cb.answer("❌ لا توجد حلقات.")
        
        buttons, row = [], []
        for (ep,) in res:
            row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"sel_q_{title_part}_{ep}"))
            if len(row) == 3: buttons.append(row); row = []
        if row: buttons.append(row)
        await cb.message.edit_text(f"📺 **قائمة الحلقات:**", reply_markup=InlineKeyboardMarkup(buttons))

    elif cb.data.startswith("sel_q_"):
        data = cb.data.replace("sel_q_", "").rsplit("_", 1)
        title_part, ep = data
        res = db_query("SELECT quality, v_id FROM videos WHERE title LIKE %s AND ep_num=%s AND status='posted'", (f"{title_part}%", ep))
        buttons = [[InlineKeyboardButton(f"💿 {q}", callback_data=f"get_vid_{v_id}")] for q, v_id in res]
        await cb.message.edit_text(f"🎬 **الحلقة {ep}**\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(buttons))

    elif cb.data.startswith("get_vid_"):
        v_id = cb.data.replace("get_vid_", "")
        db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s AND status='posted'", (v_id,))
        if res: await send_video_final(client, cb.message.chat.id, cb.from_user.id, v_id, *res[0])
        await cb.answer()

# ===== استقبال الفيديو والبوستر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    if not message.caption: return await message.reply_text("❌ أضف الاسم في وصف الفيديو.")
    series_name = clean_series_title(message.caption)
    media = message.video or message.animation or message.document
    d = getattr(media, 'duration', 0) or 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    db_query("""INSERT INTO videos (v_id, title, status, duration) VALUES (%s, %s, 'waiting', %s) 
                ON CONFLICT (v_id) DO UPDATE SET title=%s, status='waiting', duration=%s""", 
             (v_id, series_name, dur, series_name, dur), fetch=False)
    await message.reply_text(f"✅ تم حفظ الاسم: <b>{series_name}</b>\nأرسل البوستر الآن:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id, title FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return await message.reply_text("❌ أرسل الفيديو أولاً.")
    v_id, title = res[0]
    db_query("UPDATE videos SET poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(q, callback_data=f"q_{q}_{v_id}") for q in ["4K", "HD", "SD"]]])
    await message.reply_text(f"📌 {title}\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_", 2)
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن رقم الحلقة فقط:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep_num(client, message):
    if not message.text.strip().isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text.strip()
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    await publish_smartly(client, title, ep_num, p_id, dur)
    await message.reply_text(f"🚀 تم النشر/التحديث للحلقة {ep_num}.")

# ===== النشر الذكي =====
async def publish_smartly(client, title, ep_num, poster_id, duration):
    me = await client.get_me()
    res = db_query("SELECT quality, v_id FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, ep_num))
    buttons = [InlineKeyboardButton(f"🎬 {q}", url=f"https://t.me/{me.username}?start={vid}") for q, vid in res]
    markup = InlineKeyboardMarkup([buttons])
    
    old_post = db_query("SELECT post_msg_id FROM videos WHERE title=%s AND ep_num=%s AND post_msg_id IS NOT NULL LIMIT 1", (title, ep_num))
    cap = f"🎬 <b>{title}</b>\n\n📌 الحلقة: {ep_num}\n⏳ المدة: {duration}\n\n🍿 مشاهدة ممتعة!"
    
    if old_post:
        try:
            await client.edit_message_reply_markup(PUBLIC_POST_CHANNEL, int(old_post[0][0]), reply_markup=markup)
            return
        except: pass

    msg = await client.send_photo(PUBLIC_POST_CHANNEL, poster_id, caption=cap, reply_markup=markup)
    db_query("UPDATE videos SET post_msg_id=%s WHERE title=%s AND ep_num=%s", (msg.id, title, ep_num), fetch=False)

# ===== الإرسال النهائي للمستخدم =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    try:
        await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=f"📺 <b>{title}</b>\n🎞️ حلقة: {ep}\n💿 جودة: {q}\n⏳ {dur}")
    except:
        await client.send_message(chat_id, f"❌ اشترك أولاً لمشاهدة الحلقة:\n{FORCE_SUB_LINK}")

@app.on_message(filters.command("start") & filters.private)
async def start_h(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s AND status='posted'", (v_id,))
        if res: await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        await message.reply_text(f"👋 أهلاً بك! ابحث عن مسلسلك الآن.")

if __name__ == "__main__":
    app.run()
