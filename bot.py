import os
import psycopg2
import re
import logging
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307  # قناة النشر العامة

app = Client("final_stable_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return None
    btns, row, seen = [], [], set()
    me = await app.get_me()
    for vid, ep in res:
        if ep == 0 or ep in seen: continue
        seen.add(ep)
        label = f"✅ {ep}" if str(vid) == str(current_v_id) else f"{ep}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
        if len(row) == 5:
            btns.append(row)
            row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

# --- نظام الرفع والنشر (Admin) ---

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id,), fetch=False)
    await message.reply_text("✅ استلمت الفيديو. أرسل البوستر الآن وضع اسم المسلسل في الوصف.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def on_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل"
    # حفظ آيدي البوستر أيضاً للنشر لاحقاً
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    await message.reply_text(f"📌 المسلسل: {title}\nأرسل الآن **رقم الحلقة** كرسالة نصية:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "del"]))
async def on_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
    if not res: return
    
    v_id, title, p_id = res[0]
    ep = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep, v_id), fetch=False)
    
    # --- جزء النشر التلقائي في القناة العامة ---
    me = await client.get_me()
    safe_title = obfuscate_visual(title)
    pub_caption = (
        f"🎬 <b>{safe_title}</b>\n\n"
        f"<b>الحلقة: [{ep}]</b>\n"
        f"<b>الجودة: [HD]</b>\n\n"
        f"نتمنى لكم مشاهدة ممتعة."
    )
    pub_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
    ]])
    
    try:
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=pub_caption, reply_markup=pub_markup)
        await message.reply_text(f"🚀 تم الحفظ والنشر في القناة بنجاح!\nالمسلسل: {title}\nالحلقة: {ep}")
    except Exception as e:
        await message.reply_text(f"✅ تم الحفظ، ولكن فشل النشر التلقائي. الخطأ: {e}")

# --- نظام العرض (User) ---

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المشاهدة.")

    v_id = message.command[1]
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not res: return await message.reply_text("⚠️ الحلقة غير موجودة.")

    title, ep = res[0]
    markup = await get_episodes_markup(title, v_id)
    
    caption = (
        f"<b>📺 المسلسل : {obfuscate_visual(title)}</b>\n"
        f"<b>🎞️ رقم الحلقة : {ep}</b>\n\n"
        f"🍿 مشاهدة ممتعة!"
    )

    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
    except:
        await message.reply_text("⚠️ عذراً، لا يمكن الوصول للفيديو حالياً.")

if __name__ == "__main__":
    app.run()
