import os, psycopg2, logging, re, asyncio, time, random
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

# ===== [1.1] التحكم في المزيد من الحلقات =====
SHOW_MORE_BUTTONS = True

# ===== [1.2] نظام الحماية من FloodWait =====
user_last_request = {}
REQUEST_LIMIT = 5
TIME_WINDOW = 10

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] كلمات عشوائية للتشفير =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد"]

def encrypt_title(title):
    if not title: return "محتوى"
    words = title.split()
    if words:
        word = random.choice(words)
        return f"🎬 {word[::-1]} {random.randint(10,99)}"
    return f"🎬 {random.choice(ENCRYPTION_WORDS)} {random.randint(10,99)}"

# ===== [3] دالة قاعدة البيانات =====
def db_query(query, params=(), fetch=True, retry=3):
    for attempt in range(retry):
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
            logging.error(f"DB Error (attempt {attempt+1}): {e}")
            if attempt == retry - 1:
                return [] if fetch else None
            time.sleep(1)

# ===== [4] إنشاء الجداول =====
def init_database():
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, series_name TEXT, ep_num INTEGER DEFAULT 0, quality TEXT DEFAULT 'HD', views INTEGER DEFAULT 0)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS posters (poster_id BIGINT PRIMARY KEY, series_name TEXT, video_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT, first_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS pending_posts (video_id TEXT PRIMARY KEY, step TEXT, poster_id BIGINT, quality TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دوال الاستخراج المحسنة لجميع المسلسلات =====
def extract_series_name(text):
    """استخراج اسم المسلسل من النص لجميع المسلسلات"""
    if not text: return None
    
    text = text.strip()
    
    # أنماط عامة لجميع المسلسلات
    patterns = [
        # نمط: [أي اسم] الحلقة 5
        r'^(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$',
        
        # نمط: [أي اسم] 5
        r'^(.+?)\s+(\d+)$',
        
        # نمط: [أي اسم] - 5
        r'^(.+?)\s*-\s*(\d+)$',
        
        # نمط: [أي اسم] [5]
        r'^(.+?)\s*[\[\(\{]\d+[\]\)\}]',
        
        # نمط: [أي اسم] (جودة) 5
        r'^(.+?)\s+.*?\s+(\d+)$',
        
        # نمط: مسلسل [أي اسم] الحلقة 5
        r'^مسلسل\s+(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$',
        
        # نمط: مسلسل [أي اسم] 5
        r'^مسلسل\s+(.+?)\s+(\d+)$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            # تنظيف الاسم
            name = re.sub(r'[-\s]+$', '', name)
            name = re.sub(r'[\[\(\{].*$', '', name)
            return name
    
    # إذا لم ينطبق أي نمط، نأخذ النص كامل
    return text.strip()

def extract_episode_number(text):
    """استخراج رقم الحلقة من النص لجميع المسلسلات"""
    if not text: return 0
    
    text = text.strip()
    
    # 1. البحث عن رقم بعد كلمة حلقة/حلقه
    match = re.search(r'(?:حلقة|حلقه|الحلقة|الحلقه)\s*[:\-]?\s*(\d+)', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # 2. البحث عن رقم بين قوسين
    match = re.search(r'[\[\(\{](\d+)[\]\)\}]', text)
    if match:
        return int(match.group(1))
    
    # 3. البحث عن رقم بعد شرطة
    match = re.search(r'-\s*(\d+)\s*$', text)
    if match:
        return int(match.group(1))
    
    # 4. البحث عن آخر رقم في النص
    nums = re.findall(r'\d+', text)
    if nums:
        return int(nums[-1])
    
    return 0

# ===== [6] دالة جلب وتحديث بيانات الحلقة من المصدر =====
async def get_video_data_from_source(client, v_id):
    """جلب بيانات الحلقة من قناة المصدر وتحديث قاعدة البيانات"""
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        
        if not msg or not msg.video:
            return None, None, None
        
        caption = msg.caption or ""
        series_name = extract_series_name(caption)
        ep_num = extract_episode_number(caption)
        
        if not series_name:
            series_name = f"مسلسل {v_id[-3:]}"
        if ep_num == 0:
            ep_num = 1
        
        db_query(
            """INSERT INTO videos (v_id, series_name, ep_num, quality) 
               VALUES (%s, %s, %s, 'HD') 
               ON CONFLICT (v_id) DO UPDATE 
               SET series_name = EXCLUDED.series_name, 
                   ep_num = EXCLUDED.ep_num,
                   quality = COALESCE(videos.quality, 'HD')""",
            (v_id, series_name, ep_num),
            fetch=False
        )
        
        logging.info(f"🔄 تحديث تلقائي {v_id}: {series_name} - حلقة {ep_num}")
        
        return series_name, ep_num, "HD"
        
    except Exception as e:
        logging.error(f"❌ خطأ في جلب بيانات {v_id}: {e}")
        return None, None, None

# ===== [7] متابعة التعديلات على الفيديوهات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def on_video_edit(client, message):
    try:
        v_id = str(message.id)
        caption = message.caption or ""
        
        series_name = extract_series_name(caption)
        ep_num = extract_episode_number(caption)
        
        if series_name and ep_num > 0:
            db_query(
                "UPDATE videos SET series_name = %s, ep_num = %s WHERE v_id = %s",
                (series_name, ep_num, v_id),
                fetch=False
            )
            logging.info(f"✏️ تحديث يدوي {v_id}: {series_name} - حلقة {ep_num}")
    except Exception as e:
        logging.error(f"Error in on_video_edit: {e}")

# ===== [8] متابعة التعديلات على البوسترات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def on_poster_edit(client, message):
    try:
        poster_id = message.id
        new_series = extract_series_name(message.caption or "")
        if new_series:
            db_query("UPDATE posters SET series_name = %s WHERE poster_id = %s", (new_series, poster_id), fetch=False)
            video = db_query("SELECT video_id FROM posters WHERE poster_id = %s", (poster_id,))
            if video and video[0][0]:
                db_query("UPDATE videos SET series_name = %s WHERE v_id = %s", (new_series, video[0][0]), fetch=False)
                logging.info(f"✏️ تحديث بوستر {poster_id} → {new_series}")
    except Exception as e:
        logging.error(f"Error in on_poster_edit: {e}")

# ===== [9] مراقبة قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.photo))
async def monitor_source(client, message):
    try:
        if message.video:
            v_id = str(message.id)
            caption = message.caption or ""
            series_name = extract_series_name(caption)
            ep_num = extract_episode_number(caption)
            
            if series_name and ep_num > 0:
                db_query(
                    "INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, 'HD') ON CONFLICT (v_id) DO UPDATE SET series_name = EXCLUDED.series_name, ep_num = EXCLUDED.ep_num",
                    (v_id, series_name, ep_num),
                    fetch=False
                )
                logging.info(f"✅ فيديو مكتمل {v_id}: {series_name} - حلقة {ep_num}")
                await message.reply_text(f"✅ تم حفظ الفيديو: {series_name} - حلقة {ep_num}")
            else:
                db_query("INSERT INTO pending_posts (video_id, step) VALUES (%s, 'waiting_for_poster') ON CONFLICT (video_id) DO UPDATE SET step = 'waiting_for_poster'", (v_id,), fetch=False)
                await message.reply_text(f"📹 تم استلام الفيديو ({v_id})\nارفع البوستر الآن.")
        
        elif message.photo:
            poster_id = message.id
            s_name = extract_series_name(message.caption or "")
            if not s_name:
                await message.reply_text("⚠️ اكتب اسم المسلسل في وصف البوستر!")
                return
            
            pending = db_query("SELECT video_id FROM pending_posts WHERE step = 'waiting_for_poster' ORDER BY created_at DESC LIMIT 1")
            if pending:
                video_id = pending[0][0]
                db_query("INSERT INTO posters (poster_id, series_name, video_id) VALUES (%s, %s, %s)", (poster_id, s_name, video_id), fetch=False)
                db_query("UPDATE pending_posts SET step = 'waiting_for_quality', poster_id = %s WHERE video_id = %s", (poster_id, video_id), fetch=False)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("HD", callback_data=f"q_HD_{video_id}"),
                    InlineKeyboardButton("SD", callback_data=f"q_SD_{video_id}"),
                    InlineKeyboardButton("4K", callback_data=f"q_4K_{video_id}")
                ]])
                await message.reply_text(f"🖼 تم ربط {s_name}\nاختر الجودة:", reply_markup=kb)
    except Exception as e: 
        logging.error(f"Error in monitor_source: {e}")

# ===== [10] معالجة الجودة =====
@app.on_callback_query(filters.regex(r"^q_"))
async def handle_quality(client, cb):
    try:
        _, quality, v_id = cb.data.split('_')
        db_query("UPDATE pending_posts SET step = 'waiting_for_episode', quality = %s WHERE video_id = %s", (quality, v_id), fetch=False)
        await cb.message.edit_text(f"📊 الجودة: {quality}\nأرسل رقم الحلقة الآن.")
    except Exception as e:
        logging.error(f"Error in handle_quality: {e}")

# ===== [11] استقبال رقم الحلقة مع النشر التلقائي =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.regex(r"^/"))
async def receive_episode(client, message):
    try:
        ep_num = extract_episode_number(message.text)
        if ep_num == 0: return

        pending = db_query("SELECT video_id, poster_id, quality FROM pending_posts WHERE step = 'waiting_for_episode' ORDER BY created_at DESC LIMIT 1")
        if not pending: return

        v_id, p_id, q = pending[0]
        poster_data = db_query("SELECT series_name FROM posters WHERE poster_id = %s", (p_id,))
        if not poster_data: return
        s_name = poster_data[0][0]

        db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, %s)", (v_id, s_name, ep_num, q), fetch=False)
        db_query("DELETE FROM pending_posts WHERE video_id = %s", (v_id,), fetch=False)

        try:
            encrypted = encrypt_title(s_name)
            me = await client.get_me()
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
            caption = f"🎬 **{encrypted}**\n🔢 **الحلقة {ep_num}**\n📺 **الجودة {q}**"
            await client.copy_message(PUBLISH_CHANNEL, SOURCE_CHANNEL, int(p_id), caption=caption, reply_markup=btn)
            await message.reply_text(f"✅ تم النشر: {s_name} - حلقة {ep_num}")
        except Exception as e: 
            logging.error(f"Publish error: {e}")
    except Exception as e:
        logging.error(f"Error in receive_episode: {e}")

# ===== [12] نظام الحماية من FloodWait =====
def check_rate_limit(user_id):
    now = datetime.now()
    
    if user_id in user_last_request:
        user_last_request[user_id] = [
            t for t in user_last_request[user_id] 
            if now - t < timedelta(seconds=TIME_WINDOW)
        ]
    else:
        user_last_request[user_id] = []
    
    if len(user_last_request[user_id]) >= REQUEST_LIMIT:
        oldest = user_last_request[user_id][0]
        wait_time = TIME_WINDOW - (now - oldest).seconds
        return False, wait_time
    
    user_last_request[user_id].append(now)
    return True, 0

# ===== [13] أمر البدء الذكي مع التحديث التلقائي =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    
    allowed, wait_time = check_rate_limit(user_id)
    if not allowed:
        await message.reply_text(f"⏳ أنت تطلب بسرعة! انتظر {wait_time} ثانية")
        return
    
    try:
        db_query("INSERT INTO users (user_id, username, first_name, last_used) VALUES (%s, %s, %s, CURRENT_TIMESTAMP) ON CONFLICT (user_id) DO UPDATE SET last_used = CURRENT_TIMESTAMP", 
                 (user_id, message.from_user.username or "", message.from_user.first_name or ""), fetch=False)
    except:
        pass
    
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # جلب البيانات من المصدر مباشرة
        series_name, ep_num, quality = await get_video_data_from_source(client, v_id)
        
        if not series_name:
            data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
            if data:
                series_name, ep_num, quality = data[0]
            else:
                await message.reply_text("❌ لم يتم العثور على الحلقة")
                return
        
        # بناء الأزرار
        keyboard = []
        
        if SHOW_MORE_BUTTONS and series_name:
            other_eps = db_query(
                "SELECT ep_num, v_id FROM videos WHERE series_name = %s AND v_id != %s ORDER BY ep_num ASC LIMIT 30",
                (series_name, v_id)
            )
            
            if other_eps:
                row = []
                me = await client.get_me()
                bot_username = me.username
                
                row.append(InlineKeyboardButton(f"✅ {ep_num}", url=f"https://t.me/{bot_username}?start={v_id}"))
                
                for o_ep, o_vid in other_eps:
                    row.append(InlineKeyboardButton(str(o_ep), url=f"https://t.me/{bot_username}?start={o_vid}"))
                    if len(row) == 5:
                        keyboard.append(row)
                        row = []
                
                if row:
                    keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        try:
            await client.copy_message(
                message.chat.id, SOURCE_CHANNEL, int(v_id),
                caption=f"🎬 {series_name} - الحلقة {ep_num}\n📺 الجودة: {quality}",
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )
            
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
            
        except FloodWait as e:
            await message.reply_text(f"⏳ البوت مشغول، انتظر {e.value} ثانية")
            await asyncio.sleep(e.value)
            await start_cmd(client, message)
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
    else:
        welcome_text = """👋 **بوت المشاهدة الذكي**

📺 **طريقة الرفع:**
1️⃣ ارفع الفيديو
2️⃣ ارفع البوستر مع اسم المسلسل
3️⃣ اختر الجودة
4️⃣ أرسل رقم الحلقة

✅ **نشر تلقائي في قناة النشر**

🆘 @Mohsen_7e"""
        await message.reply_text(welcome_text)

# ===== [14] أوامر الإدارة =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    top = db_query("SELECT series_name, views FROM videos WHERE views > 0 ORDER BY views DESC LIMIT 5")
    
    text = f"📊 **الإحصائيات**\n📁 الحلقات: {total}\n👥 المستخدمين: {users}\n🔘 المزيد: {'✅' if SHOW_MORE_BUTTONS else '❌'}\n\n🏆 الأكثر مشاهدة:\n"
    for name, views in top:
        text += f"• {name}: {views}\n"
    
    await message.reply_text(text)

@app.on_message(filters.command("check_pending") & filters.user(ADMIN_ID))
async def check_pending(client, message):
    pending = db_query("SELECT video_id, step, quality FROM pending_posts ORDER BY created_at DESC")
    if not pending:
        await message.reply_text("📭 لا توجد طلبات معلقة")
        return
    text = "📋 **الطلبات المعلقة:**\n"
    for vid, step, q in pending:
        text += f"• {vid} | {step} | {q or '?'}\n"
    await message.reply_text(text)

@app.on_message(filters.command("reset_pending") & filters.user(ADMIN_ID))
async def reset_pending(client, message):
    db_query("DELETE FROM pending_posts", fetch=False)
    await message.reply_text("✅ تم حذف جميع الطلبات المعلقة")

@app.on_message(filters.command("test_publish") & filters.user(ADMIN_ID))
async def test_publish(client, message):
    try:
        await client.send_message(PUBLISH_CHANNEL, "🧪 اختبار النشر التلقائي")
        await message.reply_text("✅ تم إرسال رسالة اختبار")
    except Exception as e:
        await message.reply_text(f"❌ فشل الإرسال: {e}")

@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

@app.on_message(filters.command("clear_limits") & filters.user(ADMIN_ID))
async def clear_limits(client, message):
    global user_last_request
    user_last_request = {}
    await message.reply_text("✅ تم تنظيف حدود الطلبات")

@app.on_message(filters.command("update_series") & filters.user(ADMIN_ID))
async def update_series_command(client, message):
    try:
        command_parts = message.text.split(maxsplit=2)
        if len(command_parts) < 3:
            await message.reply_text("❌ استخدم: /update_series القديم الجديد")
            return
        
        old_name, new_name = command_parts[1], command_parts[2]
        videos = db_query("SELECT v_id FROM videos WHERE series_name = %s", (old_name,))
        
        if not videos:
            await message.reply_text("❌ لم يتم العثور على حلقات")
            return
        
        count = 0
        for (v_id,) in videos:
            db_query("UPDATE videos SET series_name = %s WHERE v_id = %s", (new_name, v_id), fetch=False)
            count += 1
        
        await message.reply_text(f"✅ تم تحديث {count} حلقة")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("reindex") & filters.user(ADMIN_ID))
async def reindex_command(client, message):
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            await message.reply_text("❌ استخدم: /reindex اسم_المسلسل")
            return
        
        series_name = command_parts[1]
        videos = db_query("SELECT v_id FROM videos WHERE series_name = %s", (series_name,))
        
        if not videos:
            await message.reply_text("❌ لم يتم العثور على حلقات")
            return
        
        status = await message.reply_text(f"🔄 جاري إعادة فهرسة {len(videos)} حلقة...")
        
        updated = 0
        for i, (v_id,) in enumerate(videos):
            try:
                s_name, ep_num, _ = await get_video_data_from_source(client, v_id)
                if s_name:
                    updated += 1
                
                if i % 5 == 0:
                    await status.edit_text(f"🔄 جاري التحديث... {i}/{len(videos)}")
                    
            except Exception as e:
                logging.error(f"خطأ: {e}")
        
        await status.edit_text(f"✅ تم تحديث {updated} من {len(videos)} حلقة")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [15] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل البوت الذكي مع دعم جميع المسلسلات...")
    init_database()
    
    while True:
        try:
            app.run()
        except FloodWait as e:
            wait_time = e.value
            print(f"⏳ FloodWait: انتظر {wait_time} ثانية")
            time.sleep(wait_time)
        except Exception as e:
            print(f"❌ خطأ: {e}")
            print("🔄 إعادة التشغيل بعد 5 ثواني...")
            time.sleep(5)

if __name__ == "__main__":
    main()
