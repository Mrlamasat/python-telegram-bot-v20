import os
import psycopg2
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

def init_database():
    db_query("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, joined_at TIMESTAMP DEFAULT NOW())", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS views_log (v_id TEXT, viewed_at TIMESTAMP DEFAULT NOW())", fetch=False)
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, title TEXT, poster_id TEXT, 
            ep_num INTEGER, status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0, last_view TIMESTAMP
        )
    """, fetch=False)

# ===== [3] عرض الحلقة =====
async def show_episode(client, message, v_id):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not res: return
    
    title, ep = res[0]
    # تسجيل المشاهدة في السجل اللحظي + العداد العام
    db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (v_id,), fetch=False)

    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 اضغط هنا للاشتراك بالقناه الإحتياطيه", url=BACKUP_CHANNEL_LINK)]])
    
    await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)

# ===== [4] الإحصائيات الاحترافية (يدوي بطلبك) =====
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    # أكثر 3 مسلسلات مشاهدة في آخر 24 ساعة
    top_daily = db_query("""
        SELECT v.title, COUNT(l.v_id) as d_views FROM views_log l
        JOIN videos v ON l.v_id = v.v_id WHERE l.viewed_at >= NOW() - INTERVAL '24 hours'
        GROUP BY v.title ORDER BY d_views DESC LIMIT 3
    """)

    h1 = db_query("SELECT COUNT(*) FROM views_log WHERE viewed_at >= NOW() - INTERVAL '1 hour'")[0][0]
    d24 = db_query("SELECT COUNT(*) FROM views_log WHERE viewed_at >= NOW() - INTERVAL '24 hours'")[0][0]
    u_count = db_query("SELECT COUNT(*) FROM users")[0][0]
    total_views = db_query("SELECT SUM(views) FROM videos")[0][0] or 0

    report = "<b>📊 تقرير الأداء الحالي</b>\n"
    report += "━━━━━━━━━━━━━━━\n"
    report += "<b>🔥 الأعلى مشاهدة (خلال اليوم):</b>\n"
    if top_daily:
        for i, (t, v) in enumerate(top_daily, 1):
            report += f"{i}️⃣ {t} ⇦ <code>+{v}</code>\n"
    else: report += "<i>لا توجد بيانات لليوم بعد.</i>\n"
    
    report += "━━━━━━━━━━━━━━━\n"
    report += f"<b>📈 مشاهدات آخر ساعة:</b> <code>{h1}</code>\n"
    report += f"<b>📅 مشاهدات آخر 24 ساعة:</b> <code>{d24}</code>\n"
    report += f"<b>👁️ إجمالي المشاهدات:</b> <code>{total_views:,}</code>\n"
    report += f"<b>👥 المشتركين:</b> <code>{u_count}</code>\n"
    report += f"\n📅 {datetime.now().strftime('%Y-%m-%d | %H:%M')}"

    await message.reply_text(report, parse_mode=ParseMode.HTML)

# ===== [5] نظام النشر =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
        await message.reply_text(f"✅ تم استلام الفيديو `{message.id}`")
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption, message.photo.file_id, res[0][0]), fetch=False)
            await message.reply_text(f"🖼️ تم حفظ البوستر لـ: {message.caption}")
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]; ep_num = int(message.text)
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
            me = await client.get_me()
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ اضغط هنا لمشاهدة الحلقة كاملة", url=f"https://t.me/{me.username}?start={v_id}")]])
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep_num}]</b>", reply_markup=markup)
            await message.reply_text(f"🚀 تم النشر بنجاح!")

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1: await show_episode(client, message, message.command[1])
    else: await message.reply_text(f"👋 أهلاً بك يا محمد.\nالبوت يعمل وجاهز للنشر.")

if __name__ == "__main__":
    init_database()
    app.run()
