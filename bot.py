import os, psycopg2, logging, re, asyncio, time
from datetime import datetime
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

PUBLIC_CHANNELS = [
    -1003554018307, -1003790915936, -1003678294148, -1003690441303
]

app = Client("railway_pro_v3", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دالة استخراج الرقم (شاملة للأقواس) =====
def extract_ep_num_simple(text):
    if not text: return 0
    # ترتيب الأنماط: الأقواس أولاً ثم الكلمات
    patterns = [
        r'\[(\d+)\]',                    # يمسك [17]
        r'(?:حلقه|حلقة|الحلقة|الحلقه)\s*[:\-\s]*(\d+)',
        r'رقم\s*[:\-\s]*(\d+)',
        r'#(\d+)',
        r'\((\d+)\)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match: return int(match.group(1))
    return 0

# ===== [3] دالة قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close(); conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

# ===== [4] دالة عرض الحلقة (مع الإصلاح اللحظي) =====
async def show_episode(client, message, v_id):
    try:
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        if not res: return await message.reply_text("❌ حلقة غير مسجلة.")
        
        title, ep = res[0]

        # 💡 ميزة الإصلاح اللحظي: إذا كان الرقم 0، نعيد سحبه فوراً
        if ep == 0:
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if source_msg and (source_msg.caption or source_msg.text):
                raw_text = source_msg.caption or source_msg.text
                real_ep = extract_ep_num_simple(raw_text)
                if real_ep > 0:
                    db_query("UPDATE videos SET ep_num = %s WHERE v_id = %s", (real_ep, v_id), fetch=False)
                    ep = real_ep # تحديث للعرض الحالي
                    await client.send_message(ADMIN_ID, f"🛠 تم تصحيح رقم حلقة تلقائياً:\nالمسلسل: {title}\nالرقم الجديد: {ep}")

        # جلب أزرار الحلقات الأخرى
        other_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s AND ep_num > 0 ORDER BY ep_num ASC", (title,))
        keyboard = []
        if other_eps:
            row = []
            me = await client.get_me()
            for o_ep, o_vid in other_eps:
                row.append(InlineKeyboardButton(str(o_ep), url=f"https://t.me/{me.username}?start={o_vid}"))
                if len(row) == 5: keyboard.append(row); row = []
            if row: keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])

        await client.copy_message(
            message.chat.id, SOURCE_CHANNEL, int(v_id),
            caption=f"<b>{title} - الحلقة {ep if ep > 0 else 'جاري معالجتها'}</b>",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        db_query("INSERT INTO views_log (v_id, user_id) VALUES (%s, %s)", (v_id, message.from_user.id), fetch=False)
    except Exception as e:
        logging.error(f"Show Error: {e}")

# ===== [5] أمر البداية الذكي =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    
    if len(message.command) > 1:
        v_id = message.command[1]
        # التأكد من وجودها أو إضافتها لأول مرة
        exists = db_query("SELECT 1 FROM videos WHERE v_id = %s", (v_id,))
        if not exists:
            try:
                src = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if src and (src.caption or src.text):
                    txt = src.caption or src.text
                    title = txt.split('\n')[0][:100]
                    ep = extract_ep_num_simple(txt)
                    db_query("INSERT INTO videos (v_id, title, ep_num) VALUES (%s, %s, %s)", (v_id, title, ep), fetch=False)
            except: pass
        
        await show_episode(client, message, v_id)
    else:
        await message.reply_text("👋 أهلاً بك في بوت المشاهدة الذكي.")

# ===== [6] أوامر الإدارة (Sync & Stats) =====
@app.on_message(filters.command("sync") & filters.user(ADMIN_ID))
async def sync_data(client, message):
    m = await message.reply_text("🔄 جاري مزامنة القنوات...")
    count = 0
    for ch in PUBLIC_CHANNELS:
        async for post in client.get_chat_history(ch, limit=150):
            if post.reply_markup:
                for row in post.reply_markup.inline_keyboard:
                    for btn in row:
                        if btn.url and "start=" in btn.url:
                            v_id = btn.url.split("start=")[1]
                            if not db_query("SELECT 1 FROM videos WHERE v_id = %s", (v_id,)):
                                try:
                                    src = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                                    txt = src.caption or src.text
                                    ep = extract_ep_num_simple(txt)
                                    db_query("INSERT INTO videos (v_id, title, ep_num) VALUES (%s, %s, %s)", (v_id, txt.split('\n')[0][:50], ep), fetch=False)
                                    count += 1
                                except: continue
    await m.edit_text(f"✅ تمت المزامنة! تم إضافة {count} حلقة جديدة.")

@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    zeros = db_query("SELECT COUNT(*) FROM videos WHERE ep_num = 0")[0][0]
    await message.reply_text(f"📊 إحصائيات القاعدة:\n- إجمالي الحلقات: {total}\n- حلقات برقم 0: {zeros} (سيتم إصلاحها عند الضغط)")

# ===== [7] تشغيل البوت مع نظام الحماية =====
def main():
    # إنشاء الجداول إذا لم توجد
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS views_log (id SERIAL PRIMARY KEY, v_id TEXT, user_id BIGINT, viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)

    while True:
        try:
            if os.path.exists("railway_pro_v3.session"): os.remove("railway_pro_v3.session")
            app.run()
            break
        except FloodWait as e:
            time.sleep(e.value)
        except Exception as e:
            logging.error(f"Restarting due to: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
