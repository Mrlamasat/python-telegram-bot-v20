import os
import psycopg2
import logging
import re
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7464197368 # آيدي حسابك يا محمد

app = Client("mohammed_final_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        if conn: conn.close()
        return None

def obfuscate_visual(text):
    if not text: return ""
    # تحويل "المداح" إلى "ا . ل . م . د . ا . ح"
    clean = re.sub(r'[^\w\s]', '', text).replace(" ", "")
    return " . ".join(list(clean))

# ===== محرك أزرار الحلقات (التنقل) =====
async def get_episodes_markup(title, current_v_id):
    res = db_query(
        "SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC",
        (title,)
    )
    if not res: return None
    btns, row, seen = [], [], set()
    me = await app.get_me()
    for vid, ep in res:
        if ep in seen: continue
        seen.add(ep)
        label = f"✅ {ep}" if str(vid) == str(current_v_id) else f"{ep}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
        if len(row) == 5:
            btns.append(row)
            row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

# ===== نظام استقبال البيانات (كما في كودك القديم) =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.document
    d = getattr(media, 'duration', 0)
    dur = f"{d // 3600:02}:{(d % 3600) // 60:02}:{d % 60:02}"
    
    db_query(
        "INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s",
        (v_id, dur, dur), fetch=False
    )
    await message.reply_text(f"✅ تم استلام الفيديو ({dur}). أرسل اسم المسلسل الآن في وصف (بوستر).")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل"
    db_query("UPDATE videos SET title=%s, status='awaiting_ep' WHERE v_id=%s", (title, v_id), fetch=False)
    await message.reply_text(f"📌 المسلسل: {title}\nأرسل الآن **رقم الحلقة** فقط:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & filters.reply)
async def receive_ep_manual(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id, title = res[0]
    ep_num = int(message.text)
    
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    await message.reply_text(f"🚀 تم الحفظ! المسلسل: {title} | الحلقة: {ep_num}")

# ===== أمر Start للمشاهدين =====

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك {message.from_user.first_name}!")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id = %s", (v_id,))
    
    if not res:
        return await message.reply_text("⚠️ الحلقة غير موجودة.")
    
    title, ep, q, dur = res[0]
    q = q or "HD" # جودة افتراضية
    
    markup = await get_episodes_markup(title, v_id)
    safe_title = obfuscate_visual(title)
    
    caption = (
        f"<b>📺 المسلسل : {safe_title}</b>\n"
        f"<b>🎞️ رقم الحلقة : {ep}</b>\n"
        f"<b>💿 الجودة : {q}</b>\n"
        f"<b>⏳ المدة : {dur}</b>\n\n"
        f"🍿 مشاهدة ممتعة نتمناها لكم!"
    )

    try:
        await client.copy_message(
            message.chat.id, SOURCE_CHANNEL, int(v_id),
            caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML
        )
    except:
        await message.reply_text("⚠️ عذراً، لم أتمكن من جلب الفيديو.")

if __name__ == "__main__":
    app.run()
