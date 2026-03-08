import os, psycopg2, logging, re, asyncio, time
from datetime import datetime
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

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دالة قاعدة البيانات =====
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

# ===== [3] إنشاء الجدول =====
def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0
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

# ===== [4] دالة استخراج الرقم =====
def extract_ep(text):
    if not text:
        return 0
    match = re.search(r'(\d+)', text)
    return int(match.group(1)) if match else 0

# ===== [5] أمر الاختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [6] أمر البدء =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
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
            msg = await message.reply_text("🔄 جاري التحميل...")
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and source.video:
                    text = source.caption or ""
                    title = text.split('\n')[0][:50] if text else "فيديو"
                    ep = extract_ep(text)
                    
                    # حفظ في قاعدة البيانات
                    db_query(
                        "INSERT INTO videos (v_id, title, ep_num) VALUES (%s, %s, %s)",
                        (v_id, title, ep),
                        fetch=False
                    )
                    
                    await msg.delete()
                    
                    # عرض الحلقة
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)
                    ]])
                    
                    await client.copy_message(
                        message.chat.id,
                        SOURCE_CHANNEL,
                        int(v_id),
                        caption=f"<b>{title} - الحلقة {ep}</b>",
                        reply_markup=keyboard
                    )
                    
                    # زيادة المشاهدات
                    db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
                else:
                    await msg.edit_text("❌ الحلقة غير موجودة")
            except Exception as e:
                await msg.edit_text(f"❌ خطأ: {e}")
        else:
            title, ep = data[0]
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)
            ]])
            
            await client.copy_message(
                message.chat.id,
                SOURCE_CHANNEL,
                int(v_id),
                caption=f"<b>{title} - الحلقة {ep}</b>",
                reply_markup=keyboard
            )
            
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        await message.reply_text("👋 أهلاً بك في البوت")

# ===== [7] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    
    top = db_query("""
        SELECT title, views FROM videos 
        WHERE views > 0 
        ORDER BY views DESC 
        LIMIT 5
    """)
    
    text = f"📊 **الإحصائيات**\n\n"
    text += f"📁 الحلقات: {total}\n"
    text += f"👥 المستخدمين: {users}\n\n"
    text += "🏆 **الأكثر مشاهدة:**\n"
    
    for title, views in top:
        text += f"• {title}: {views} مشاهدة\n"
    
    await message.reply_text(text)

# ===== [8] مراقبة التعديلات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def on_edit(client, message):
    if message.video and message.caption:
        v_id = str(message.id)
        text = message.caption
        title = text.split('\n')[0][:50]
        ep = extract_ep(text)
        
        db_query(
            "UPDATE videos SET title = %s, ep_num = %s WHERE v_id = %s",
            (title, ep, v_id),
            fetch=False
        )
        logging.info(f"✅ تم تحديث الحلقة {v_id}")

# ===== [9] التشغيل =====
def main():
    print("🚀 تشغيل البوت...")
    init_db()
    
    try:
        app.run()
    except FloodWait as e:
        print(f"⏳ انتظر {e.value} ثانية")
        time.sleep(e.value)
    except Exception as e:
        print(f"❌ خطأ: {e}")

if __name__ == "__main__":
    main()
