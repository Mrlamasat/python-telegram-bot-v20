import os
import psycopg2
import psycopg2.pool
import logging
import re
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import PeerIdInvalid, FloodWait

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

app = Client("mohammed_bot_vfinal", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات =====
db_pool = None
def get_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")
    return db_pool

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        pool = get_pool()
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return res
    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

def init_db():
    db_query("""CREATE TABLE IF NOT EXISTS videos (
        v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, 
        poster_id TEXT, quality TEXT, duration TEXT, 
        status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0
    )""", fetch=False)
    cols = [("ep_num","INTEGER"), ("poster_id","TEXT"), ("quality","TEXT"), ("duration","TEXT"), ("views","INTEGER DEFAULT 0"), ("status","TEXT DEFAULT 'waiting'"), ("title","TEXT")]
    for c, t in cols: db_query(f"ALTER TABLE videos ADD COLUMN IF NOT EXISTS {c} {t}", fetch=False)

# ===== أدوات المعالجة =====
def clean_and_decode(text):
    if not text: return "مسلسل"
    cleaned = text.replace(".", "").replace(" ", "").strip()
    cleaned = re.sub(r'(الحلقة|حلقة).*', '', cleaned)
    return cleaned

def obfuscate_visual(text):
    return " . ".join(list(text)) if text else ""

async def get_episodes_markup(title, current_v_id):
    """توليد أزرار الحلقات مع ضمان عدم إرسال قائمة فارغة تسبب خطأ 400"""
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return None
    
    btns, row, seen = [], [], set()
    me = await app.get_me()
    for vid, ep in res:
        if ep in seen: continue
        seen.add(ep)
        label = f"✅ {ep}" if str(vid) == str(current_v_id) else f"{ep}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
        if len(row) == 5: btns.append(row); row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns) if btns else None

# ===== المزامنة (ID Scan) للقنوات الخاصة =====
@app.on_message(filters.command("sync") & filters.user(ADMIN_ID))
async def sync_handler(client, message):
    msg = await message.reply_text("🔄 جاري المزامنة الذكية للقناة الخاصة...")
    count = 0
    try:
        # استخدام get_chat_history مع limit محدود لتجنب BOT_METHOD_INVALID
        async for m in client.get_chat_history(PUBLIC_POST_CHANNEL, limit=300):
            if m and m.caption and m.reply_markup:
                try:
                    url = m.reply_markup.inline_keyboard[0][0].url
                    v_id = url.split("start=")[1]
                    title_match = re.search(r"المسلسل\s*:\s*(.*)\n", m.caption)
                    clean_t = clean_and_decode(title_match.group(1)) if title_match else "مسلسل"
                    ep_m = re.search(r"رقم الحلقة\s*:\s*(\d+)", m.caption)
                    ep = int(ep_m.group(1)) if ep_m else 0
                    
                    db_query("""INSERT INTO videos (v_id, title, ep_num, status) 
                               VALUES (%s, %s, %s, 'posted') 
                               ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, status='posted'""",
                            (v_id, clean_t, ep, clean_t, ep), fetch=False)
                    count += 1
                except: continue
        await msg.edit_text(f"✅ تمت المزامنة بنجاح! الحلقات المكتشفة: {count}")
    except Exception as e:
        await msg.edit_text(f"❌ فشل المزامنة: {e}\n(تأكد من توجيه رسالة من القناة للبوت)")

# ===== دالة الإرسال النهائي =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    try:
        # التحديث التلقائي للبيانات 0
        if ep == 0 or not title or title == "مسلسل":
            try:
                source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source_msg and source_msg.caption:
                    title = clean_and_decode(source_msg.caption)
                    ep_m = re.search(r'(\d+)', source_msg.caption)
                    ep = int(ep_m.group(1)) if ep_m else ep
                    db_query("UPDATE videos SET title=%s, ep_num=%s WHERE v_id=%s", (title, ep, v_id), fetch=False)
            except: pass

        markup = await get_episodes_markup(title, v_id)
        
        # فحص الاشتراك
        is_sub = True
        try:
            member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
            if member.status in ["left", "kicked"]: is_sub = False
        except: is_sub = False

        cap = (f"<b>📺 المسلسل : {obfuscate_visual(title)}</b>\n"
               f"<b>🎞️ رقم الحلقة : {ep}</b>\n\n🍿 مشاهدة ممتعة!")

        kb = []
        if not is_sub: kb.append([InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)])
        
        # دمج الأزرار بحذر
        final_markup = None
        if markup:
            # إذا كان هناك أزرار حلقات، ندمجها مع زر الاشتراك
            current_kb = markup.inline_keyboard
            if not is_sub:
                current_kb = [[InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)]] + current_kb
            final_markup = InlineKeyboardMarkup(current_kb)
        elif not is_sub:
            final_markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)]])

        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=final_markup)
    except Exception as e:
        logging.error(f"❌ Error sending: {e}")
        await client.send_message(chat_id, "⚠️ الفيديو غير متاح حالياً في المصدر.")

# ===== معالجات الأوامر =====
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً {message.from_user.first_name}! أرسل رابط الحلقة للمشاهدة.")
    
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, "مسلسل", 0, "HD", "00:00")

# (بقية الدوال handle_new_video, handle_poster, handle_ep_num تضاف هنا كما في النسخ السابقة)

# ===== التشغيل =====
async def main():
    await app.start()
    logging.info("🚀 تنشيط القنوات...")
    for c in [SOURCE_CHANNEL, PUBLIC_POST_CHANNEL]:
        try: await app.get_chat(c)
        except: pass
    await idle()
    await app.stop()

if __name__ == "__main__":
    init_db()
    app.run(main())
