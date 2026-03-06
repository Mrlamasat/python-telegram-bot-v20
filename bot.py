import os
import psycopg2
import logging
import re
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
SOURCE_CHANNEL = -1003547072209 

app = Client("mohammed_bot_final_fixed", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# قائمة المسلسلات الذكية للمطابقة
MY_SERIES = [
    "اولاد الراعي", "كلهم بيحبو مودي", "الست موناليزا", "فن الحرب",
    "افراج", "الكاميرا الخفيه", "رامز ليفل الوحش", "صحاب الارض",
    "وننسى اللي كان", "علي كلاي", "عين سحريه", "فخر الدلتا",
    "الكينج", "درش", "راس الافعى", "المداح", "هي كيميا", "سوا سوا",
    "بيبو", "النص الثاني", "عرض وطلب", "مولانا", "فرصه اخيره",
    "حكايه نرجس", "اب ولكن", "اللون الازرق", "المتر سمير",
    "بابا وماما جيران", "قطر صغنطوط", "ن النسوه"
]

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
    except:
        if conn: conn.close()
        return None

def extract_smart_data(caption):
    """محرك استخراج الاسم والرقم بالذكاء"""
    # 1. استخراج الاسم من القائمة
    title = "مسلسل"
    for s in MY_SERIES:
        if s in caption:
            title = s.replace(" ", "").strip()
            break
            
    # 2. استخراج الرقم بنظام (رقم الحلقة: X) أو السطر الأخير
    ep = 0
    match = re.search(r'رقم الحلقة\s*:?\s*(\d+)', caption)
    if match:
        ep = int(match.group(1))
    else:
        lines = [l.strip() for l in caption.split('\n') if l.strip()]
        if lines and lines[-1].isdigit():
            ep = int(lines[-1])
            
    return title, ep

def visual_name(title):
    return " . ".join(list(title))

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s ORDER BY ep_num ASC", (title,))
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

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك {message.from_user.first_name}!")
    
    v_id = message.command[1].strip()
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    title, ep = (res[0] if res and res[0] else (None, None))

    # إذا كانت البيانات قديمة (صفر) أو غير موجودة، نصححها فوراً من المصدر
    if not title or ep == 0:
        try:
            m = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if m and m.caption:
                title, ep = extract_smart_data(m.caption)
                db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s", (v_id, title, ep, title, ep), fetch=False)
        except:
            if not title: title, ep = "مسلسل", 0

    markup = await get_episodes_markup(title, v_id)
    caption = f"<b>📺 المسلسل : {visual_name(title)}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n\n🍿 مشاهدة ممتعة!"

    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
    except:
        await message.reply_text("⚠️ الحلقة غير متوفرة.")

async def main():
    await app.start()
    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
