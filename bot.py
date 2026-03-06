import os
import psycopg2
import re
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# ===== الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
SOURCE_CHANNEL = -1003547072209  # قناة المصدر الأساسية
PUBLIC_CHANNEL = -1003554018307  # قناة النشر (التي فيها الكلمات المفتاحية)

app = Client("smart_auto_fix_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def db_query(query, params=(), fetch=True):
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    cur.execute(query, params)
    res = cur.fetchall() if fetch else (conn.commit() or None)
    cur.close()
    conn.close()
    return res

def extract_episode_number(text):
    """المستخرج الذكي من الكلمات المفتاحية"""
    if not text: return 0
    # يبحث عن (حلقة رقم أو الحلقة أو حلقة) يتبعها رقم، مع دعم الأقواس [ ] أو :
    patterns = [
        r'(?:حلقة رقم|الحلقة|حلقة)\s*[:\s]*\[?(\d+)\]?', # يبحث عن "حلقة رقم 5" أو "الحلقة: [5]"
        r'(\d+)' # احتياط: أول رقم يظهر في النص
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return 0

def visual_name(title):
    if not title: return "مسلسل"
    clean = re.sub(r'[^\w\s]', '', title).replace(" ", "")
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

@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك في بوت المشاهدة!")

    v_id = message.command[1]
    # جلب البيانات الحالية من القاعدة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    
    title = res[0][0] if res else "مسلسل"
    ep_num = res[0][1] if res else 0

    # التنشيط التلقائي: إذا كان الرقم 0، يبحث عنه في المصدر أو النشر فوراً
    if ep_num == 0:
        try:
            # نحاول جلب الرسالة من قناة المصدر أولاً
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if source_msg and source_msg.caption:
                ep_num = extract_episode_number(source_msg.caption)
                # إذا وجدنا الرقم، نحدث قاعدة البيانات فوراً
                if ep_num > 0:
                    db_query("UPDATE videos SET ep_num = %s WHERE v_id = %s", (ep_num, v_id), fetch=False)
        except Exception as e:
            print(f"Error auto-fixing: {e}")

    markup = await get_episodes_markup(title, v_id)
    caption = (
        f"<b>📺 المسلسل : {visual_name(title)}</b>\n"
        f"<b>🎞️ رقم الحلقة : {ep_num}</b>\n\n"
        f"🍿 مشاهدة ممتعة!"
    )

    try:
        await client.copy_message(
            message.chat.id, SOURCE_CHANNEL, int(v_id),
            caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML
        )
    except:
        await message.reply_text("⚠️ لم يتم العثور على الحلقة.")

if __name__ == "__main__":
    app.run()
