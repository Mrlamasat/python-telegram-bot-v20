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
            series_name TEXT,  -- اسم المسلسل (من البوستر)
            ep_num INTEGER DEFAULT 0,  -- رقم الحلقة (من الفيديو)
            encrypted_name TEXT,  -- اسم مشفر للنشر
            poster_id INTEGER,  -- معرف البوستر المرتبط
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # جدول البوسترات
    db_query("""
        CREATE TABLE IF NOT EXISTS posters (
            poster_id INTEGER PRIMARY KEY,
            series_name TEXT,  -- اسم المسلسل
            encrypted_name TEXT,  -- اسم مشفر للنشر
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # جدول الربط بين الفيديوهات والبوسترات
    db_query("""
        CREATE TABLE IF NOT EXISTS video_poster_link (
            video_id TEXT PRIMARY KEY,
            poster_id INTEGER,
            linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    """استخراج اسم المسلسل من أي نص"""
    if not text:
        return None
    # إزالة الأرقام من النص
    clean_text = re.sub(r'\s*\d+\s*$', '', text.strip())
    clean_text = re.sub(r'^\d+\s*', '', clean_text)
    return clean_text.strip()[:100]

def extract_episode_number(text):
    """استخراج رقم الحلقة من أي نص"""
    if not text:
        return 0
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 0

# ===== [6] مراقبة البوسترات الجديدة والمعدلة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def handle_poster(client, message):
    """معالجة البوسترات (الصور)"""
    if not message.photo:
        return
    
    poster_id = message.id
    new_series_name = extract_series_name(message.caption or "")
    
    if not new_series_name:
        return
    
    encrypted = encrypt_title(new_series_name)
    
    # التحقق مما إذا كان هذا بوستر موجود مسبقاً
    existing = db_query("SELECT series_name FROM posters WHERE poster_id = %s", (poster_id,))
    
    if existing:
        # هذا تعديل على بوستر قديم
        old_name = existing[0][0]
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
        
        logging.info(f"✏️ تحديث بوستر {poster_id}: {old_name} → {new_series_name}")
    else:
        # هذا بوستر جديد
        db_query("""
            INSERT INTO posters (poster_id, series_name, encrypted_name) 
            VALUES (%s, %s, %s)
        """, (poster_id, new_series_name, encrypted), fetch=False)
        
        logging.info(f"🖼 بوستر جديد {poster_id}: {new_series_name}")

# ===== [7] مراقبة الفيديوهات الجديدة والمعدلة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def handle_video(client, message):
    """معالجة الفيديوهات"""
    if not message.video:
        return
    
    v_id = str(message.id)
    new_ep = extract_episode_number(message.caption or "")
    
    # البحث عن آخر بوستر قبل هذا الفيديو (خلال آخر 50 رسالة)
    poster = db_query("""
        SELECT poster_id, series_name, encrypted_name FROM posters 
        WHERE poster_id < %s 
        ORDER BY poster_id DESC LIMIT 1
    """, (int(v_id),))
    
    if not poster:
        logging.warning(f"⚠️ لا يوجد بوستر للفيديو {v_id}")
        return
    
    poster_id, series_name, encrypted = poster[0]
    
    # التحقق مما إذا كان هذا الفيديو موجود مسبقاً
    existing = db_query("SELECT ep_num FROM videos WHERE v_id = %s", (v_id,))
    
    if existing:
        # هذا تعديل على فيديو قديم
        old_ep = existing[0][0]
        if new_ep > 0:
            db_query("""
                UPDATE videos 
                SET ep_num = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE v_id = %s
            """, (new_ep, v_id), fetch=False)
            logging.info(f"✏️ تحديث فيديو {v_id}: حلقة {old_ep} → {new_ep}")
    else:
        # هذا فيديو جديد
        if new_ep == 0:
            new_ep = 1  # قيمة افتراضية
        
        db_query("""
            INSERT INTO videos (v_id, series_name, ep_num, encrypted_name, poster_id) 
            VALUES (%s, %s, %s, %s, %s)
        """, (v_id, series_name, new_ep, encrypted, poster_id), fetch=False)
        
        # ربط الفيديو بالبوستر
        db_query("""
            INSERT INTO video_poster_link (video_id, poster_id) 
            VALUES (%s, %s)
        """, (v_id, poster_id), fetch=False)
        
        logging.info(f"🎬 فيديو جديد {v_id}: {series_name} - حلقة {new_ep} (بوستر {poster_id})")

# ===== [8] دالة إنشاء أزرار الحلقات =====
def create_episode_buttons(series_name, current_v_id, bot_username):
    """إنشاء أزرار الحلقات الأخرى من نفس المسلسل"""
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

# ===== [9] أمر البدء =====
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
            # جلب من المصدر مباشرة
            msg = await message.reply_text("🔄 جاري التحميل...")
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and source.video:
                    # محاولة العثور على بوستر
                    poster = db_query("""
                        SELECT poster_id, series_name, encrypted_name FROM posters 
                        WHERE poster_id < %s 
                        ORDER BY poster_id DESC LIMIT 1
                    """, (int(v_id),))
                    
                    if not poster:
                        await msg.edit_text("❌ لا يوجد بوستر لهذا المسلسل")
                        return
                    
                    poster_id, series_name, encrypted = poster[0]
                    ep = extract_episode_number(source.caption or "")
                    
                    if ep == 0:
                        ep = 1
                    
                    # حفظ الفيديو
                    db_query("""
                        INSERT INTO videos (v_id, series_name, ep_num, encrypted_name, poster_id) 
                        VALUES (%s, %s, %s, %s, %s)
                    """, (v_id, series_name, ep, encrypted, poster_id), fetch=False)
                    
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

# ===== [10] أمر النشر في القناة =====
@app.on_message(filters.command("publish") & filters.user(ADMIN_ID))
async def publish_cmd(client, message):
    cmd = message.text.split()
    if len(cmd) < 2:
        await message.reply_text("❌ استخدم: /publish v_id")
        return
    
    v_id = cmd[1]
    
    try:
        data = db_query("""
            SELECT v.series_name, v.ep_num, v.encrypted_name, p.poster_id 
            FROM videos v
            LEFT JOIN posters p ON v.poster_id = p.poster_id
            WHERE v.v_id = %s
        """, (v_id,))
        
        if not data:
            await message.reply_text("❌ الحلقة غير موجودة في قاعدة البيانات")
            return
        
        series_name, ep, encrypted, poster_id = data[0]
        
        # رابط البوت
        me = await client.get_me()
        bot_link = f"https://t.me/{me.username}?start={v_id}"
        
        button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 مشاهدة الحلقة", url=bot_link)
        ]])
        
        # إذا كان لدينا بوستر، نستخدمه
        if poster_id:
            try:
                await client.copy_message(
                    PUBLISH_CHANNEL,
                    SOURCE_CHANNEL,
                    poster_id,
                    caption=f"{encrypted}\nالحلقة {ep}",
                    reply_markup=button
                )
            except:
                # إذا فشل، نرسل رسالة نصية
                await client.send_message(
                    PUBLISH_CHANNEL,
                    f"{encrypted}\nالحلقة {ep}",
                    reply_markup=button
                )
        else:
            # رسالة نصية فقط
            await client.send_message(
                PUBLISH_CHANNEL,
                f"{encrypted}\nالحلقة {ep}",
                reply_markup=button
            )
        
        await message.reply_text(f"✅ تم النشر: {encrypted} - حلقة {ep}")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [11] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total_videos = db_query("SELECT COUNT(*) FROM videos")[0][0]
    total_posters = db_query("SELECT COUNT(*) FROM posters")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    
    top = db_query("""
        SELECT series_name, views FROM videos 
        WHERE views > 0 
        ORDER BY views DESC 
        LIMIT 5
    """)
    
    text = f"📊 **الإحصائيات**\n\n"
    text += f"📁 الفيديوهات: {total_videos}\n"
    text += f"🖼 البوسترات: {total_posters}\n"
    text += f"👥 المستخدمين: {users}\n"
    text += f"🔘 المزيد من الحلقات: {'✅ مفعل' if SHOW_MORE_BUTTONS else '❌ معطل'}\n\n"
    text += "🏆 **الأكثر مشاهدة:**\n"
    
    for name, views in top:
        text += f"• {name}: {views} مشاهدة\n"
    
    await message.reply_text(text)

# ===== [12] أمر اختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [13] أمر عرض البوسترات =====
@app.on_message(filters.command("posters") & filters.user(ADMIN_ID))
async def posters_cmd(client, message):
    posters = db_query("""
        SELECT poster_id, series_name, encrypted_name, created_at 
        FROM posters 
        ORDER BY poster_id DESC 
        LIMIT 10
    """)
    
    if not posters:
        await message.reply_text("لا توجد بوسترات")
        return
    
    text = "🖼 **آخر 10 بوسترات:**\n\n"
    for pid, name, enc, date in posters:
        text += f"• {pid}: {name} → {enc}\n"
    
    await message.reply_text(text)

# ===== [14] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل البوت الذكي مع ربط البوسترات...")
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
