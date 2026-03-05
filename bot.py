import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== الدوال المساعدة =====
def obfuscate_visual(text):
    return " . ".join(list(text)) if text else ""

def clean_series_title(text):
    if not text: return "مسلسل"
    text = re.sub(r'https?://\S+', '', text)
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return []
    btns, row, seen = [], [], set()
    me = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen: continue
        seen.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={v_id}"))
        if len(row) == 5: btns.append(row); row = []
    if row: btns.append(row)
    return btns

# ===== نظام معالجة الطلبات (Start) مع ميزة "البحث الذكي" =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا <b>{escape(message.from_user.first_name)}</b>!")
    
    v_id_key = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id_key,))
    if not res: return await message.reply_text("❌ الحلقة غير مسجلة.")
    
    title, ep, q, dur = res[0]
    user_id = message.from_user.id

    # فحص الاشتراك (استثناء الأدمن)
    if user_id != ADMIN_ID:
        try:
            m = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
            if m.status in ["left", "kicked"]:
                return await message.reply_text("⚠️ اشترك لمشاهدة الحلقة 👇", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        except: pass

    # محاولة جلب الفيديو بذكاء لتجنب Empty Message
    target_v_id = int(v_id_key)
    try:
        # فحص الرسالة الأصلية والرسائل المحيطة بها (بحد أقصى 2 رسائل للخلف)
        found_msg = None
        for i in range(3):
            check_id = target_v_id - i
            msg = await client.get_messages(SOURCE_CHANNEL, check_id)
            if msg and (msg.video or msg.document or msg.animation):
                found_msg = msg
                break
        
        if not found_msg:
            return await message.reply_text("⚠️ عذراً، لم يتم العثور على ملف الفيديو في قناة المصدر.")

        btns = await get_episodes_markup(title, v_id_key)
        safe_t = obfuscate_visual(escape(title))
        cap = (f"<b>📺 المسلسل : {safe_t}</b>\n"
               f"<b>🎞️ رقم الحلقة : {ep}</b>\n"
               f"<b>💿 الجودة : {q}</b>\n"
               f"<b>⏳ المدة : {dur}</b>\n\n🍿 مشاهدة ممتعة!")

        await client.copy_message(message.chat.id, SOURCE_CHANNEL, found_msg.id, caption=cap, reply_markup=InlineKeyboardMarkup(btns))
        db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id_key,), fetch=False)
    except Exception as e:
        logging.error(f"Copy Error: {e}")
        await message.reply_text("❌ فشل جلب الفيديو من المصدر.")

# ===== نظام الاستقبال والنشر (اليدوي) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = getattr(media, 'duration', 0)
    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو ({dur}). أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='aq' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: {title}\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_q(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='ae' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ جودة {q}. أرسل الآن رقم الحلقة فقط:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='ae' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur, ep = *res[0], int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep, v_id), fetch=False)
    me = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    cap = (f"🎬 <b>{safe_t}</b>\n\n<b>الحلقة: [{ep}]</b>\n<b>الجودة: [{q}]</b>\n<b>المدة: [{dur}]</b>\n\n🍿 مشاهدة ممتعة.")
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    await client.send_photo(PUBLIC_POST_CHANNEL, p_id, caption=cap, reply_markup=markup)
    await message.reply_text("🚀 نُشرت بنجاح!")

if __name__ == "__main__":
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, poster_id TEXT, quality TEXT, duration TEXT, status TEXT, views INTEGER DEFAULT 0)", fetch=False)
    app.run()
