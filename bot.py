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
SHOW_MORE_BUTTONS = True

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] كلمات عشوائية للتشفير =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد", "حلقة", "مسلسل"]

def encrypt_title(title):
    """تشفير اسم المسلسل للقناة"""
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
            poster_id INTEGER,
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # جدول البوسترات
    db_query("""
        CREATE TABLE IF NOT EXISTS posters (
            poster_id INTEGER PRIMARY KEY,
            series_name TEXT,
            encrypted_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # جدول المستخدمين
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دوال الاستخراج =====
def extract_series_name(text):
    """استخراج اسم المسلسل من النص"""
    if not text:
        return None
    # إزالة الأرقام من النهاية
    clean_text = re.sub(r'\s*\d+\s*$', '', text.strip())
    clean_text = re.sub(r'^\d+\s*', '', clean_text)
    return clean_text.strip()[:100]

def extract_episode_number(text):
    """استخراج رقم الحلقة من النص"""
    if not text:
        return 0
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 0

# ===== [6] مراقبة البوسترات =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def handle_poster(client, message):
    """معالجة البوسترات الجديدة والمعدلة"""
    if not message.photo:
        return
    
    poster_id = message.id
    new_series_name = extract_series_name(message.caption or "")
    
    if not new_series_name:
        return
    
    encrypted = encrypt_title(new_series_name)
    
    # التحقق مما إذا كان البوستر موجوداً
    existing = db_query("SELECT series_name FROM posters WHERE poster_id = %s", (poster_id,))
    
    if existing:
        # تحديث بوستر قديم
        db_query("""
            UPDATE posters 
            SET series_name = %s, encrypted_name = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE poster_id = %s
        """, (new_series_name, encrypted, poster_id), fetch=False)
        
        # تحديث جميع الفيديوهات المرتبطة بهذا البوستر
        db_query("""
            UPDATE videos 
            SET series_name = %s, encrypted_name = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE poster_id = %s
        """, (new_series_name, encrypted, poster_id), fetch=False)
        
        logging.info(f"✏️ تحديث بوستر {poster_id}: {new_series_name}")
    else:
        # إضافة بوستر جديد
        db_query("""
            INSERT INTO posters (poster_id, series_name, encrypted_name) 
            VALUES (%s, %s, %s)
        """, (poster_id, new_series_name, encrypted), fetch=False)
        logging.info(f"🖼 بوستر جديد {poster_id}: {new_series_name}")

# ===== [7] مراقبة الفيديوهات =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def handle_video(client, message):
    """معالجة الفيديوهات الجديدة والمعدلة"""
    if not message.video:
        return
    
    v_id = str(message.id)
    new_ep = extract_episode_number(message.caption or "")
    
    # البحث عن آخر بوستر
    poster = db_query("""
        SELECT poster_id, series_name, encrypted_name FROM posters 
        WHERE poster_id < %s 
        ORDER BY poster_id DESC LIMIT 1
    """, (int(v_id),))
    
    # التحقق مما إذا كان الفيديو موجوداً
    existing = db_query("SELECT ep_num FROM videos WHERE v_id = %s", (v_id,))
    
    if existing:
        # تحديث فيديو قديم
        if new_ep > 0:
            db_query("UPDATE videos SET ep_num = %s, updated_at = CURRENT_TIMESTAMP WHERE v_id = %s", 
                    (new_ep, v_id), fetch=False)
            logging.info(f"✏️ تحديث فيديو {v_id} → حلقة {new_ep}")
    else:
        # فيديو جديد
        if poster:
            # يوجد بوستر - نستخدمه
            poster_id, series_name, encrypted = poster[0]
            if new_ep == 0:
                new_ep = 1
            db_query("""
                INSERT INTO videos (v_id, series_name, ep_num, encrypted_name, poster_id) 
                VALUES (%s, %s, %s, %s, %s)
            """, (v_id, series_name, new_ep, encrypted, poster_id), fetch=False)
            logging.info(f"🎬 فيديو جديد {v_id}: {series_name} - حلقة {new_ep} (بوستر {poster_id})")
        else:
            # لا يوجد بوستر - نستخدم اسم مؤقت
            temp_name = f"مسلسل {random.randint(100,999)}"
            encrypted = encrypt_title(temp_name)
            if new_ep == 0:
                new_ep = 1
            db_query("""
                INSERT INTO videos (v_id, series_name, ep_num, encrypted_name) 
                VALUES (%s, %s, %s, %s)
            """, (v_id, temp_name, new_ep, encrypted), fetch=False)
            logging.info(f"🎬 فيديو جديد {v_id}: {temp_name} - حلقة {new_ep} (بدون بوستر)")

# ===== [8] دالة إنشاء أزرار الحلقات =====
def create_episode_buttons(series_name, current_v_id, bot_username):
    """إنشاء أزرار الحلقات الأخرى"""
    other_eps = db_query("""
        SELECT ep_num, v_id FROM videos 
        WHERE series_name = %s AND ep_num > 0 AND v_id != %s
        ORDER BY ep_num ASC
        LIMIT 30
    """, (series_name, current_v_id))
    
    if not other_eps:
        return []
    
    keyboard = []
    row = []
    
    for i, (ep, vid) in enumerate(other_eps, 1):
        row.append(InlineKeyboardButton(
            str(ep), 
            url=f"https://t.me/{bot_username}?start={vid}"
        ))
        if i % 5 == 0:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    return keyboard

# ===== [9] أمر البدء (معدل للفيديوهات القديمة) =====
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
        
        # البحث في قاعدة البيانات
        data = db_query("SELECT series_name, ep_num, encrypted_name FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            # الفيديو غير موجود في قاعدة البيانات - نجربه直接从 المصدر
            msg = await message.reply_text("🔄 جاري التحميل لأول مرة...")
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and source.video:
                    # استخراج المعلومات من الفيديو
                    ep = extract_episode_number(source.caption or "")
                    if ep == 0:
                        ep = 1
                    
                    # استخراج اسم المسلسل من caption (للفيديوهات القديمة)
                    series_name = extract_series_name(source.caption or "")
                    if not series_name:
                        series_name = f"مسلسل {v_id[-3:]}"
                    
                    encrypted = encrypt_title(series_name)
                    
                    # حفظ الفيديو في قاعدة البيانات
                    db_query("""
                        INSERT INTO videos (v_id, series_name, ep_num, encrypted_name) 
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (v_id) DO NOTHING
                    """, (v_id, series_name, ep, encrypted), fetch=False)
                    
                    await msg.delete()
                    
                    # بناء الأزرار
                    keyboard = []
                    me = await client.get_me()
                    
                    if SHOW_MORE_BUTTONS:
                        more_buttons = create_episode_buttons(series_name, v_id, me.username)
                        if more_buttons:
                            keyboard.extend(more_buttons)
                    
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
            # الفيديو موجود في قاعدة البيانات
            series_name, ep, encrypted = data[0]
            
            # بناء الأزرار
            keyboard = []
            me = await client.get_me()
            
            if SHOW_MORE_BUTTONS:
                more_buttons = create_episode_buttons(series_name, v_id, me.username)
                if more_buttons:
                    keyboard.extend(more_buttons)
            
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
        await message.reply_text("👋 بوت المشاهدة الذكي")

# ===== [10] أمر فحص وإصلاح قاعدة البيانات =====
@app.on_message(filters.command("fix_db") & filters.user(ADMIN_ID))
async def fix_database(client, message):
    msg = await message.reply_text("🔄 جاري فحص وإصلاح قاعدة البيانات...")
    
    # جلب جميع الفيديوهات التي ليس لها series_name
    videos_to_fix = db_query("""
        SELECT v_id FROM videos 
        WHERE series_name IS NULL OR series_name = ''
    """)
    
    fixed = 0
    for (v_id,) in videos_to_fix:
        try:
            source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if source and source.video:
                series_name = extract_series_name(source.caption or "")
                if not series_name:
                    series_name = f"مسلسل {v_id[-3:}"
                
                ep = extract_episode_number(source.caption or "")
                if ep == 0:
                    ep = 1
                
                encrypted = encrypt_title(series_name)
                
                db_query("""
                    UPDATE videos 
                    SET series_name = %s, ep_num = %s, encrypted_name = %s 
                    WHERE v_id = %s
                """, (series_name, ep, encrypted, v_id), fetch=False)
                fixed += 1
        except:
            continue
    
    await msg.edit_text(f"✅ تم إصلاح {fixed} فيديو")

# ===== [11] أمر النشر =====
@app.on_message(filters.command("publish") & filters.user(ADMIN_ID))
async def publish_cmd(client, message):
    cmd = message.text.split()
    if len(cmd) < 2:
        await message.reply_text("❌ استخدم: /publish v_id")
        return
    
    v_id = cmd[1]
    
    try:
        data = db_query("SELECT series_name, ep_num, encrypted_name FROM videos WHERE v_id = %s", (v_id,))
        if not data:
            await message.reply_text("❌ الحلقة غير موجودة في قاعدة البيانات")
            return
        
        series_name, ep, encrypted = data[0]
        
        me = await client.get_me()
        bot_link = f"https://t.me/{me.username}?start={v_id}"
        
        button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 مشاهدة الحلقة", url=bot_link)
        ]])
        
        await client.send_message(
            PUBLISH_CHANNEL,
            f"{encrypted}\nالحلقة {ep}",
            reply_markup=button
        )
        
        await message.reply_text(f"✅ تم النشر: {encrypted} - حلقة {ep}")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [12] أمر الإحصائيات =====
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
    text += f"🔘 المزيد: {'✅' if SHOW_MORE_BUTTONS else '❌'}\n\n"
    text += "🏆 **الأكثر مشاهدة:**\n"
    
    for name, views in top:
        text += f"• {name}: {views}\n"
    
    await message.reply_text(text)

# ===== [13] أمر اختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [14] التشغيل الرئيسي =====
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
