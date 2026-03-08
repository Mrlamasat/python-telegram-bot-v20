import os, psycopg2, logging, re, asyncio, time
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
PUBLISH_CHANNEL = -1003554018307

# ===== [2] تشغيل البوت =====
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [3] دالة قاعدة بيانات بسيطة =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else None
        conn.commit()
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

# ===== [4] إنشاء الجداول =====
def init_database():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            quality TEXT,
            duration TEXT,
            views_today INTEGER DEFAULT 0,
            views_total INTEGER DEFAULT 0
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            last_seen TIMESTAMP
        )
    """, fetch=False)
    
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دالة استخراج اسم ورقم الحلقة =====
def extract_title_ep(text):
    if not text:
        return None, 0
    match = re.search(r'^(.+?)\s+(\d+)$', text.strip().split('\n')[0])
    if match:
        return match.group(1).strip(), int(match.group(2))
    return text[:50], 0

# ===== [6] أمر الاختبار الأول =====
@app.on_message(filters.command("test") & filters.private)
async def test_command(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [7] أمر البدء =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    # تسجيل المستخدم
    db_query(
        "INSERT INTO users (user_id, username, last_seen) VALUES (%s, %s, NOW()) ON CONFLICT (user_id) DO UPDATE SET last_seen = NOW()",
        (message.from_user.id, message.from_user.username or ""),
        fetch=False
    )
    
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # بحث في قاعدة البيانات
        data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            # جلب من المصدر
            waiting = await message.reply_text("🔄 جاري التحميل...")
            try:
                msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if msg and msg.video:
                    text = msg.caption or ""
                    title, ep = extract_title_ep(text)
                    if ep == 0:
                        ep = 1
                    
                    db_query(
                        "INSERT INTO videos (v_id, title, ep_num) VALUES (%s, %s, %s)",
                        (v_id, title, ep),
                        fetch=False
                    )
                    await waiting.delete()
                    
                    # عرض الحلقة
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)
                    ]])
                    
                    await client.copy_message(
                        message.chat.id,
                        SOURCE_CHANNEL,
                        int(v_id),
                        caption=f"🎬 الحلقة {ep}",
                        reply_markup=keyboard
                    )
                    
                    # تسجيل المشاهدة
                    db_query(
                        "UPDATE videos SET views_today = views_today + 1, views_total = views_total + 1 WHERE v_id = %s",
                        (v_id,),
                        fetch=False
                    )
                else:
                    await waiting.edit_text("❌ الحلقة غير موجودة")
            except Exception as e:
                await waiting.edit_text(f"❌ خطأ: {e}")
        else:
            title, ep = data[0]
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)
            ]])
            
            await client.copy_message(
                message.chat.id,
                SOURCE_CHANNEL,
                int(v_id),
                caption=f"🎬 الحلقة {ep}",
                reply_markup=keyboard
            )
            
            db_query(
                "UPDATE videos SET views_today = views_today + 1, views_total = views_total + 1 WHERE v_id = %s",
                (v_id,),
                fetch=False
            )
    else:
        await message.reply_text("👋 أهلاً بك في البوت")

# ===== [8] أمر الإحصائيات المبسط =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_command(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    views = db_query("SELECT SUM(views_total) FROM videos")[0][0] or 0
    
    top = db_query("""
        SELECT title, views_total FROM videos 
        WHERE views_total > 0 
        ORDER BY views_total DESC 
        LIMIT 5
    """)
    
    text = f"📊 **الإحصائيات**\n\n"
    text += f"📁 الحلقات: {total}\n"
    text += f"👥 المستخدمين: {users}\n"
    text += f"👀 المشاهدات: {views}\n\n"
    text += "🏆 **الأكثر مشاهدة:**\n"
    
    for title, v in top:
        text += f"• {title}: {v} مشاهدة\n"
    
    await message.reply_text(text)

# ===== [9] أمر إضافة حلقة يدوياً =====
@app.on_message(filters.command("add") & filters.user(ADMIN_ID))
async def add_command(client, message):
    cmd = message.text.split()
    if len(cmd) < 3:
        await message.reply_text("❌ استخدم: /add v_id ep_num")
        return
    
    v_id = cmd[1]
    ep = int(cmd[2])
    
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if msg and msg.video:
            title, _ = extract_title_ep(msg.caption or "")
            db_query(
                "INSERT INTO videos (v_id, title, ep_num) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET ep_num = %s",
                (v_id, title, ep, ep),
                fetch=False
            )
            await message.reply_text(f"✅ تم إضافة الحلقة {ep}")
        else:
            await message.reply_text("❌ الفيديو غير موجود")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [10] مراقبة التعديلات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def on_edit(client, message):
    if message.video and message.caption:
        v_id = str(message.id)
        title, ep = extract_title_ep(message.caption)
        if ep > 0:
            db_query(
                "UPDATE videos SET title = %s, ep_num = %s WHERE v_id = %s",
                (title, ep, v_id),
                fetch=False
            )
            logging.info(f"✅ تم تحديث الحلقة {v_id} إلى {ep}")

# ===== [11] التشغيل =====
def main():
    print("🚀 تشغيل البوت...")
    init_database()
    
    try:
        app.run()
    except FloodWait as e:
        print(f"⏳ انتظر {e.value} ثانية")
        time.sleep(e.value)
    except Exception as e:
        print(f"❌ خطأ: {e}")

if __name__ == "__main__":
    main()
