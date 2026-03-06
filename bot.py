import os
import psycopg2
import re
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
ADMIN_ID = 7464197368 

app = Client("ramadan_final_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# متغيرات لتخزين بيانات البوت لتجنب FloodWait
BOT_INFO = {"username": None, "id": None}

def db_query(query, params=(), fetch=True):
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(query, params)
    res = cur.fetchall() if fetch else (conn.commit() or None)
    cur.close()
    conn.close()
    return res

def obfuscate_visual(text):
    if not text: return "مسلسل"
    clean = re.sub(r'[^\w\s]', '', text).replace(" ", "")
    return " . ".join(list(clean))

async def get_bot_username():
    """تجلب يوزرنيم البوت مرة واحدة وتخزنه"""
    if not BOT_INFO["username"]:
        me = await app.get_me()
        BOT_INFO["username"] = me.username
        BOT_INFO["id"] = me.id
    return BOT_INFO["username"]

async def get_episodes_markup(title, current_v_id):
    username = await get_bot_username()
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return None
    
    btns, row, seen = [], [], set()
    for vid, ep in res:
        if ep == 0 or ep in seen: continue
        seen.add(ep)
        label = f"✅ {ep}" if str(vid) == str(current_v_id) else f"{ep}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{username}?start={vid}"))
        if len(row) == 5:
            btns.append(row)
            row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

# --- نظام الإحصائيات (Stats) ---

@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def get_rich_stats(client, message):
    # إحصائيات اليوم، الأسبوع، والعام
    today_q = "SELECT title, SUM(views) FROM videos WHERE last_view >= CURRENT_DATE GROUP BY title ORDER BY SUM(views) DESC LIMIT 3"
    week_q = "SELECT title, SUM(views) FROM videos WHERE last_view >= CURRENT_DATE - INTERVAL '7 days' GROUP BY title ORDER BY SUM(views) DESC LIMIT 3"
    total_q = "SELECT title, SUM(views) FROM videos GROUP BY title ORDER BY SUM(views) DESC LIMIT 5"
    
    today_res = db_query(today_q)
    week_res = db_query(week_q)
    total_res = db_query(total_q)

    text = "📊 <b>تقرير الأداء الذكي</b>\n\n"
    text += "📅 <b>اليوم:</b>\n" + ("\n".join([f"• {obfuscate_visual(t)} ({v})" for t,v in today_res]) if today_res else "• لا مشاهدات")
    text += "\n\n🗓️ <b>هذا الأسبوع:</b>\n" + ("\n".join([f"• {obfuscate_visual(t)} ({v})" for t,v in week_res]) if week_res else "• لا بيانات")
    text += "\n\n🌍 <b>الأكثر مشاهدة عامة:</b>\n" + ("\n".join([f"• {obfuscate_visual(t)} ({v})" for t,v in total_res]) if total_res else "• القائمة فارغة")
    
    await message.reply_text(text, parse_mode=ParseMode.HTML)

# --- نظام الرفع والنشر التلقائي ---

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id,), fetch=False)
    await message.reply_text("✅ فيديو مستلم. أرسل البوستر مع اسم المسلسل:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def on_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل"
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 {title}\nأرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def on_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    
    v_id, title, p_id = res[0]
    ep = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep, v_id), fetch=False)
    
    # النشر التلقائي
    username = await get_bot_username()
    pub_caption = f"🎬 <b>{obfuscate_visual(title)}</b>\n\n<b>الحلقة: [{ep}]</b>\n<b>الجودة: [HD]</b>"
    pub_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{username}?start={v_id}")]])
    
    try:
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=pub_caption, reply_markup=pub_markup)
        await message.reply_text(f"🚀 تم الحفظ والنشر بنجاح! (حلقة {ep})")
    except Exception as e:
        await message.reply_text(f"⚠️ تم الحفظ ولكن فشل النشر: {e}")

# --- نظام العرض (User) ---

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً يا محمد، ابدأ المشاهدة من قنواتنا!")

    v_id = message.command[1]
    
    # تحديث العداد والتاريخ
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1, last_view = CURRENT_TIMESTAMP WHERE v_id = %s", (v_id,), fetch=False)
    
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not res: return await message.reply_text("⚠️ غير موجود.")

    title, ep = res[0]
    markup = await get_episodes_markup(title, v_id)
    caption = f"<b>📺 المسلسل : {obfuscate_visual(title)}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n\n🍿 مشاهدة ممتعة!"

    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
    except:
        await message.reply_text("⚠️ الفيديو غير متاح حالياً.")

if __name__ == "__main__":
    app.run()
