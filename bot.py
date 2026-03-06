import os
import psycopg2
import re
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
ADMIN_ID = 7464197368 

# تغيير اسم الجلسة لضمان استقرار الاتصال
app = Client("railway_stable_v3", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# تخزين معلومات البوت في الذاكرة لتجنب FloodWait
BOT_INFO = {"username": None}

def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=5)
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

def obfuscate_visual(text):
    if not text: return "مسلسل"
    clean = re.sub(r'[^\w\s]', '', text).replace(" ", "")
    return " . ".join(list(clean))

async def get_cached_username():
    if not BOT_INFO["username"]:
        me = await app.get_me()
        BOT_INFO["username"] = me.username
    return BOT_INFO["username"]

# --- نظام الإحصائيات المطور ---
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def get_rich_stats(client, message):
    today_q = "SELECT title, SUM(views) FROM videos WHERE last_view >= CURRENT_DATE GROUP BY title ORDER BY SUM(views) DESC LIMIT 3"
    total_q = "SELECT title, SUM(views) FROM videos GROUP BY title ORDER BY SUM(views) DESC LIMIT 5"
    
    today_res = db_query(today_q)
    total_res = db_query(total_q)

    text = "📊 <b>تقرير الأداء:</b>\n\n"
    text += "📅 <b>اليوم:</b>\n" + ("\n".join([f"• {obfuscate_visual(t)} ({v})" for t,v in today_res]) if today_res else "• لا مشاهدات")
    text += "\n\n🌍 <b>الأكثر مشاهدة عامة:</b>\n" + ("\n".join([f"• {obfuscate_visual(t)} ({v})" for t,v in total_res]) if total_res else "• فارغ")
    await message.reply_text(text)

# --- نظام الرفع والنشر ---
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id,), fetch=False)
    await message.reply_text("✅ تم استلام الفيديو. أرسل البوستر الآن:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def on_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id, title = res[0][0], message.caption or "مسلسل"
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 المسلسل: {title}\nأرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def on_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    
    v_id, title, p_id, ep = res[0][0], res[0][1], res[0][2], int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep, v_id), fetch=False)
    
    username = await get_cached_username()
    pub_caption = f"🎬 <b>{obfuscate_visual(title)}</b>\n\n<b>الحلقة: [{ep}]</b>"
    pub_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{username}?start={v_id}")]])
    
    await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=pub_caption, reply_markup=pub_markup)
    await message.reply_text(f"🚀 تم النشر بنجاح!")

# --- نظام العرض للمشتركين ---
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد!")

    v_id = message.command[1]
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1, last_view = CURRENT_TIMESTAMP WHERE v_id = %s", (v_id,), fetch=False)
    
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not res: return await message.reply_text("⚠️ غير موجود.")

    title, ep = res[0]
    username = await get_cached_username()
    
    # جلب قائمة الحلقات للأزرار
    ep_res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    btns, row, seen = [], [], set()
    for vid, e_n in ep_res:
        if e_n == 0 or e_n in seen: continue
        seen.add(e_n)
        label = f"✅ {e_n}" if str(vid) == str(v_id) else f"{e_n}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{username}?start={vid}"))
        if len(row) == 5:
            btns.append(row); row = []
    if row: btns.append(row)

    caption = f"<b>📺 {obfuscate_visual(title)} - حلقة {ep}</b>"
    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(btns))

if __name__ == "__main__":
    app.run()
