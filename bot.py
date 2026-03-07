import os, psycopg2, logging
from datetime import datetime
from pyrogram import Client, filters, errors
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
        cur.close(); conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

# ===== [3] نظام الإصلاح الديناميكي =====
async def dynamic_fix_and_send(client, message, title, ep_num):
    """يبحث عن الفيديو في القناة إذا فشل المعرف المخزن"""
    logging.info(f"🔍 محاولة إصلاح ديناميكي لـ: {title} حلقة {ep_num}")
    
    # البحث في آخر 300 رسالة في قناة المصدر
    async for msg in client.get_chat_history(SOURCE_CHANNEL, limit=300):
        content = (msg.caption or msg.text or "").lower()
        if title.lower() in content and str(ep_num) in content:
            new_v_id = str(msg.id)
            # تحديث القاعدة فوراً بالمعرف الجديد الصحيح
            db_query("UPDATE videos SET v_id = %s WHERE title = %s AND ep_num = %s", (new_v_id, title, ep_num), fetch=False)
            
            # محاولة الإرسال بالمعرف الجديد
            return await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=SOURCE_CHANNEL,
                message_id=msg.id,
                caption=f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep_num}</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)]])
            )
    return None

async def show_episode(client, message, v_id):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not res:
        await message.reply_text("❌ لم يتم العثور على بيانات الحلقة.")
        return
    
    title, ep = res[0]
    
    try:
        # المحاولة الأولى: النسخ المباشر
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)]])
        )
    except Exception as e:
        logging.warning(f"⚠️ فشل الإرسال التقليدي ({e})، يبدأ الإصلاح الديناميكي...")
        
        # المحاولة الثانية: البحث التلقائي عن الفيديو وتصحيح المعرف
        fixed = await dynamic_fix_and_send(client, message, title, ep)
        
        if not fixed:
            # المحاولة الثالثة: التوجيه (Forward) كحل أخير
            try:
                await client.forward_messages(message.chat.id, SOURCE_CHANNEL, int(v_id))
            except:
                await message.reply_text("❌ عذراً، الفيديو غير متاح في قناة المصدر حالياً.")
    
    # تحديث الإحصائيات
    db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (v_id,), fetch=False)

# ===== [4] بقية الأوامر (Stats / Source Handler / Start) بنفس منطقك =====
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    d24 = db_query("SELECT COUNT(*) FROM views_log WHERE viewed_at >= NOW() - INTERVAL '24 hours'")[0][0]
    u_count = db_query("SELECT COUNT(*) FROM users")[0][0]
    await message.reply_text(f"📊 مشتركين: {u_count}\n👁️ مشاهدات 24س: {d24}")

@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO NOTHING", (str(message.id),), fetch=False)
        await message.reply_text(f"✅ تم استلام فيديو {message.id}")
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
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep_num}]</b>", reply_markup=markup)
            await message.reply_text(f"🚀 تم النشر!")

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1: await show_episode(client, message, message.command[1])
    else: await message.reply_text(f"👋 أهلاً بك يا محمد. البوت جاهز.")

if __name__ == "__main__":
    app.run()
