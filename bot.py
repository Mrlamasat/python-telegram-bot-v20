import os, psycopg2, logging, re, asyncio, time, random
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
PUBLISH_CHANNEL = -1003554018307

# ===== [1.1] التحكم في المزيد من الحلقات =====
SHOW_MORE_BUTTONS = True  # غير إلى False لو عايز تعطل

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دوال التشفير =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد"]

def encrypt_title(title):
    if not title:
        return "محتوى"
    words = title.split()
    if words:
        word = random.choice(words)
        return f"🎬 {word[::-1]} {random.randint(10,99)}"
    return f"🎬 {random.choice(ENCRYPTION_WORDS)} {random.randint(10,99)}"

# ===== [3] دالة قاعدة البيانات =====
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
    # جدول الفيديوهات
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            series_name TEXT,
            ep_num INTEGER DEFAULT 0,
            encrypted_name TEXT,
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دوال الاستخراج =====
def extract_series_name(text):
    if not text:
        return None
    clean = re.sub(r'\s*\d+\s*$', '', text.strip())
    return clean.strip()[:50]

def extract_episode_number(text):
    if not text:
        return 0
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 0

# ===== [6] دالة أزرار الحلقات =====
def get_episode_buttons(series_name, current_id, bot_user):
    if not series_name:
        return []
    
    eps = db_query("""
        SELECT ep_num, v_id FROM videos 
        WHERE series_name = %s AND v_id != %s
        ORDER BY ep_num ASC LIMIT 30
    """, (series_name, current_id))
    
    if not eps:
        return []
    
    keyboard, row = [], []
    for i, (ep, vid) in enumerate(eps, 1):
        row.append(InlineKeyboardButton(str(ep), url=f"https://t.me/{bot_user}?start={vid}"))
        if i % 5 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return keyboard

# ===== [7] أمر البدء =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    # تسجيل المستخدم
    db_query(
        "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_seen = CURRENT_TIMESTAMP",
        (message.from_user.id, message.from_user.username or ""),
        fetch=False
    )
    
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # بحث في قاعدة البيانات
        data = db_query("SELECT series_name, ep_num, encrypted_name FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            msg = await message.reply_text("🔄 جاري التحميل...")
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and source.video:
                    # استخراج المعلومات
                    ep = extract_episode_number(source.caption or "")
                    if ep == 0:
                        ep = 1
                    
                    series = extract_series_name(source.caption or "")
                    if not series:
                        series = f"مسلسل {v_id[-3:]}"
                    
                    encrypted = encrypt_title(series)
                    
                    # حفظ في قاعدة البيانات
                    db_query("""
                        INSERT INTO videos (v_id, series_name, ep_num, encrypted_name) 
                        VALUES (%s, %s, %s, %s)
                    """, (v_id, series, ep, encrypted), fetch=False)
                    
                    await msg.delete()
                    
                    # بناء الأزرار
                    keyboard = []
                    me = await client.get_me()
                    
                    if SHOW_MORE_BUTTONS:
                        more = get_episode_buttons(series, v_id, me.username)
                        if more:
                            keyboard.extend(more)
                    
                    keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
                    
                    await client.copy_message(
                        message.chat.id,
                        SOURCE_CHANNEL,
                        int(v_id),
                        caption=f"<b>🎬 الحلقة {ep}</b>",
                        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
                    )
                    
                    db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
                else:
                    await msg.edit_text("❌ الحلقة غير موجودة")
            except Exception as e:
                await msg.edit_text(f"❌ خطأ: {e}")
        else:
            series, ep, encrypted = data[0]
            
            keyboard = []
            me = await client.get_me()
            
            if SHOW_MORE_BUTTONS:
                more = get_episode_buttons(series, v_id, me.username)
                if more:
                    keyboard.extend(more)
            
            keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
            
            await client.copy_message(
                message.chat.id,
                SOURCE_CHANNEL,
                int(v_id),
                caption=f"<b>🎬 الحلقة {ep}</b>",
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )
            
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        await message.reply_text("👋 بوت المشاهدة")

# ===== [8] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    top = db_query("SELECT series_name, views FROM videos WHERE views > 0 ORDER BY views DESC LIMIT 5")
    
    text = f"📊 **الإحصائيات**\n📁 الحلقات: {total}\n🔘 المزيد: {'✅' if SHOW_MORE_BUTTONS else '❌'}\n\n🏆 الأكثر مشاهدة:\n"
    for name, views in top:
        text += f"• {name}: {views}\n"
    
    await message.reply_text(text)

# ===== [9] أمر اختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [10] التشغيل =====
def main():
    print("🚀 تشغيل البوت...")
    init_database()
    
    try:
        app.run()
    except FloodWait as e:
        print(f"⏳ انتظر {e.value} ثانية")
        time.sleep(e.value)

if __name__ == "__main__":
    main()
