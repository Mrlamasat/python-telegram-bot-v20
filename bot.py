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
ADMIN_ID = 7464197368 

app = Client("mohammed_smart_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== محرك الذكاء لاستخراج اسم المسلسل =====
def smart_extract_title(caption):
    if not caption: return "مسلسل"
    
    # تقسيم النص إلى أسطر وتنظيفها
    lines = [l.strip() for l in caption.split('\n') if l.strip()]
    
    candidate_title = "مسلسل"
    for line in lines[:3]: # فحص أول 3 أسطر بحثاً عن الاسم
        # حذف الإيموجي والرموز الخاصة
        clean_line = re.sub(r'[^\w\s]', '', line).strip()
        # حذف الأرقام والكلمات المساعدة
        clean_line = re.sub(r'\d+', '', clean_line)
        for word in ["الحلقة", "حلقة", "مشاهدة", "اضغط", "هنا", "جديدة", "فيديو", "وصف"]:
            clean_line = clean_line.replace(word, "")
        
        clean_line = clean_line.strip()
        if len(clean_line) > 1: # إذا وجدنا نصاً حقيقياً وليس مجرد رمز
            candidate_title = clean_line
            break
            
    return candidate_title.replace(" ", "").replace("_", "")

def visual_name(title):
    """عرض الاسم بنقاط بشكل احترافي"""
    return " . ".join(list(title))

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

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s ORDER BY ep_num ASC", (title,))
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

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك {message.from_user.first_name}!")
    
    v_id = message.command[1].strip()
    
    # محاولة جلب البيانات
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    title, ep = (res[0] if res and res[0] else (None, None))

    # إذا كان الاسم رمزاً أو غير موجود، نستخدم الاستخراج الذكي
    if not title or len(title) < 2 or ep == 0:
        try:
            m = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if m and m.caption:
                title = smart_extract_title(m.caption)
                ep_match = re.search(r'(\d+)', m.caption)
                ep = int(ep_match.group(1)) if ep_match else 0
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
