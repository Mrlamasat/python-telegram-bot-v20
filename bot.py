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
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7464197368 # تأكد من وضع الآيدي الخاص بك هنا

app = Client("mohammed_bot_fixed", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- دالة التحقق من الاشتراك (محسنة) ---
async def is_subscribed(client, user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        # إذا حدث خطأ تقني أو البوت ليس أدمن في القناة، نسمح للمستخدم بالمرور
        logging.error(f"Subscription Check Error: {e}")
        return True 
    return False

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

def clean_name(text):
    if not text: return "مسلسل"
    t = re.sub(r'[^\w\s]', '', text)
    return t.replace(".", "").replace(" ", "").strip()

def visual_name(text):
    clean = clean_name(text)
    return " . ".join(list(clean))

async def get_episodes_markup(title, current_v_id):
    search_title = clean_name(title)
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s ORDER BY ep_num ASC", (search_title,))
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
    
    # 1. فحص الاشتراك الإجباري أولاً
    if not await is_subscribed(client, message.from_user.id):
        return await message.reply_text(
            f"⚠️ عذراً يا {message.from_user.first_name}، يجب عليك الاشتراك في القناة أولاً لتتمكن من المشاهدة.\n\n{FORCE_SUB_LINK}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 اضغط هنا للاشتراك", url=FORCE_SUB_LINK)]])
        )

    # 2. جلب البيانات والتصحيح التلقائي
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    title, ep = (res[0] if res and res[0] else (None, None))

    if not title or ep == 0:
        try:
            m = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if m and m.caption:
                lines = [l.strip() for l in m.caption.split('\n') if l.strip()]
                title = clean_name(lines[0])
                ep_match = re.search(r'\[(\d+)\]', m.caption) or re.search(r'(\d+)', m.caption)
                ep = int(ep_match.group(1)) if ep_match else 0
                db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s", (v_id, title, ep, title, ep), fetch=False)
        except:
            if not title: title, ep = "مسلسل", 0

    # 3. الإرسال
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
