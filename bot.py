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
SHOW_MORE_BUTTONS = True  # تأكد أنه True

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] كلمات عشوائية للتشفير =====
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
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            series_name TEXT,
            ep_num INTEGER DEFAULT 0,
            encrypted_name TEXT,
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دوال الاستخراج =====
def extract_episode_number(text):
    if not text:
        return 0
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 0

def extract_series_name(text):
    if not text:
        return "مسلسل"
    clean = re.sub(r'\s*\d+\s*$', '', text.strip())
    clean = re.sub(r'^\d+\s*', '', clean)
    if not clean:
        return "مسلسل"
    return clean.strip()[:50]

# ===== [6] دالة أزرار الحلقات =====
def get_episode_buttons(series_name, current_id, bot_user):
    if not series_name:
        return []
    
    eps = db_query("""
        SELECT ep_num, v_id FROM videos 
        WHERE series_name = %s 
        ORDER BY ep_num ASC LIMIT 50
    """, (series_name,))
    
    if not eps:
        return []
    
    keyboard, row = [], []
    for ep, vid in eps:
        label = f"• {ep} •" if str(vid) == str(current_id) else str(ep)
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_user}?start={vid}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return keyboard

# ===== [7] أمر البدء =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query(
        "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_seen = CURRENT_TIMESTAMP",
        (message.from_user.id, message.from_user.username or ""),
        fetch=False
    )
    
    if len(message.command) > 1:
        v_id = message.command[1]
        me = await client.get_me()
        
        data = db_query("SELECT series_name, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and (source.video or source.document):
                    ep = extract_episode_number(source.caption or "")
                    series = extract_series_name(source.caption or "")
                    
                    db_query("""
                        INSERT INTO videos (v_id, series_name, ep_num) 
                        VALUES (%s, %s, %s) ON CONFLICT (v_id) DO NOTHING
                    """, (v_id, series, ep), fetch=False)
                    
                    current_series, current_ep = series, ep
                else:
                    return await message.reply_text("❌ لم يتم العثور على الفيديو.")
            except Exception as e:
                return await message.reply_text(f"⚠️ خطأ: {e}")
        else:
            current_series, current_ep = data[0]
            if not current_series:
                current_series = "مسلسل"

        # توليد الأزرار
        keyboard = []
        if SHOW_MORE_BUTTONS:
            more_buttons = get_episode_buttons(current_series, v_id, me.username)
            if more_buttons:
                keyboard.extend(more_buttons)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=f"<b>🎬 {current_series} - الحلقة {current_ep}</b>",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
        
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        await message.reply_text("👋 أهلاً بك في بوت المشاهدة.")

# ===== [8] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    
    top = db_query("""
        SELECT series_name, views FROM videos 
        WHERE views > 0 
        ORDER BY views DESC 
        LIMIT 5
    """)
    
    text = f"📊 **الإحصائيات**\n\n"
    text += f"📁 الحلقات: {total}\n"
    text += f"👥 المستخدمين: {users}\n"
    text += f"🔘 المزيد: {'✅ مفعل' if SHOW_MORE_BUTTONS else '❌ معطل'}\n\n"
    text += "🏆 **الأكثر مشاهدة:**\n"
    
    for name, views in top:
        text += f"• {name}: {views} مشاهدة\n"
    
    await message.reply_text(text)

# ===== [9] أمر تشخيص الأزرار =====
@app.on_message(filters.command("debug_buttons") & filters.user(ADMIN_ID))
async def debug_buttons(client, message):
    cmd = message.text.split()
    if len(cmd) < 2:
        await message.reply_text("❌ استخدم: /debug_buttons v_id")
        return
    
    v_id = cmd[1]
    
    current = db_query("SELECT series_name, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not current:
        await message.reply_text("❌ الحلقة غير موجودة في قاعدة البيانات")
        return
    
    series, ep = current[0]
    
    others = db_query("""
        SELECT v_id, ep_num FROM videos 
        WHERE series_name = %s AND v_id != %s
        ORDER BY ep_num ASC
    """, (series, v_id))
    
    text = f"🔍 **تشخيص أزرار المزيد**\n\n"
    text += f"📌 الحلقة الحالية:\n"
    text += f"• v_id: {v_id}\n"
    text += f"• المسلسل: {series}\n"
    text += f"• رقم الحلقة: {ep}\n\n"
    
    text += f"⚙️ الإعدادات:\n"
    text += f"• SHOW_MORE_BUTTONS: {'✅ مفعل' if SHOW_MORE_BUTTONS else '❌ معطل'}\n\n"
    
    text += f"📊 حلقات أخرى في نفس المسلسل: {len(others)}\n"
    
    if others:
        text += "قائمة الحلقات الأخرى:\n"
        for vid, ep_num in others[:10]:
            text += f"• حلقة {ep_num} (v_id: {vid})\n"
    else:
        text += "❌ لا توجد حلقات أخرى لنفس المسلسل!\n"
        text += "هذا هو سبب عدم ظهور الأزرار."
    
    await message.reply_text(text)

# ===== [10] أمر توحيد أسماء المسلسلات =====
@app.on_message(filters.command("fix_series") & filters.user(ADMIN_ID))
async def fix_series_names(client, message):
    msg = await message.reply_text("🔄 جاري توحيد أسماء المسلسلات...")
    
    all_series = db_query("""
        SELECT DISTINCT series_name FROM videos 
        WHERE series_name IS NOT NULL
    """)
    
    fixed = 0
    for (name,) in all_series:
        if not name:
            continue
        
        clean_name = re.sub(r'\s+', ' ', name.strip())
        clean_name = re.sub(r'[^\w\s]', '', clean_name)
        
        if clean_name != name:
            db_query("""
                UPDATE videos SET series_name = %s 
                WHERE series_name = %s
            """, (clean_name, name), fetch=False)
            fixed += 1
    
    await msg.edit_text(f"✅ تم توحيد {fixed} اسم مسلسل")

# ===== [11] أمر إصلاح قاعدة البيانات =====
@app.on_message(filters.command("fix_db") & filters.user(ADMIN_ID))
async def fix_database(client, message):
    msg = await message.reply_text("🔄 جاري إصلاح قاعدة البيانات...")
    
    videos = db_query("SELECT v_id FROM videos WHERE series_name IS NULL OR series_name = ''")
    fixed = 0
    
    for (v_id,) in videos:
        try:
            source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if source and source.video:
                series = extract_series_name(source.caption or "")
                ep = extract_episode_number(source.caption or "")
                db_query("UPDATE videos SET series_name = %s, ep_num = %s WHERE v_id = %s", 
                        (series, ep, v_id), fetch=False)
                fixed += 1
        except:
            continue
    
    await msg.edit_text(f"✅ تم إصلاح {fixed} فيديو")

# ===== [12] أمر اختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [13] التشغيل =====
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
