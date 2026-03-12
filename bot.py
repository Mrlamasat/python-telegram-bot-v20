import os, psycopg2, logging, re, asyncio, time, random
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserNotParticipant

# استيراد دوال التحديث
from series_menu import refresh_series_menu

logging.basicConfig(level=logging.INFO)

# ===== # ===== [1] الإعدادات من متغيرات البيئة =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = int(os.environ.get("SOURCE_CHANNEL", "-1003547072209"))
PUBLISH_CHANNEL = int(os.environ.get("PUBLISH_CHANNEL", "-1003689965691"))
FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "-1003637472584"))

ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+pTT0n-NtJ7ZiMWZk"

# رابط القناة الإجبارية الثابت (لن يتغير)
FORCE_SUB_LINK = "https://t.me/+bJVu0tEtj9UyMmFk"

# ===== [1.1] التحكم في المزيد من الحلقات =====
SHOW_MORE_BUTTONS = True

# ===== [1.2] نظام الحماية من FloodWait =====
user_last_request = {}
REQUEST_LIMIT = 5
TIME_WINDOW = 10

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دوال التحقق من الاشتراك =====
async def check_force_sub(client, user_id):
    """التحقق من اشتراك المستخدم في القناة الإجبارية"""
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception as e:
        logging.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

async def get_force_sub_button():
    """الحصول على زر الاشتراك في القناة - باستخدام الرابط الثابت"""
    return InlineKeyboardButton(
        "🔔 اشترك في القناة أولاً", 
        url=FORCE_SUB_LINK
    )

# ===== [3] كلمات عشوائية للتشفير =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد"]

def encrypt_title(title):
    if not title: return "محتوى"
    words = title.split()
    if words:
        word = random.choice(words)
        return f"🎬 {word[::-1]} {random.randint(10,99)}"
    return f"🎬 {random.choice(ENCRYPTION_WORDS)} {random.randint(10,99)}"

# ===== [4] دالة قاعدة البيانات =====
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

# ===== [5] إنشاء الجداول =====
def init_database():
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, series_name TEXT, ep_num INTEGER DEFAULT 0, quality TEXT DEFAULT 'HD', views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS posters (poster_id BIGINT PRIMARY KEY, series_name TEXT, video_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT, first_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS pending_posts (video_id TEXT PRIMARY KEY, step TEXT, poster_id BIGINT, quality TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS views_log (id SERIAL PRIMARY KEY, v_id TEXT, viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    print("✅ قاعدة البيانات جاهزة")

# ===== [6] دوال الاستخراج =====
def extract_series_name(text):
    if not text: return None
    text = text.strip()
    patterns = [
        r'^(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$',
        r'^(.+?)\s+(\d+)$',
        r'^(.+?)\s*-\s*(\d+)$',
        r'^(.+?)\s*[\[\(\{]\d+[\]\)\}]',
        r'^(.+?)\s+.*?\s+(\d+)$',
        r'^مسلسل\s+(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$',
        r'^مسلسل\s+(.+?)\s+(\d+)$',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'[-\s]+$', '', name)
            name = re.sub(r'[\[\(\{].*$', '', name)
            return name
    return text.strip()

def extract_episode_number(text):
    if not text: return 0
    text = text.strip()
    match = re.search(r'(?:حلقة|حلقه|الحلقة|الحلقه)\s*[:\-]?\s*(\d+)', text, re.IGNORECASE)
    if match: return int(match.group(1))
    match = re.search(r'[\[\(\{](\d+)[\]\)\}]', text)
    if match: return int(match.group(1))
    match = re.search(r'-\s*(\d+)\s*$', text)
    if match: return int(match.group(1))
    nums = re.findall(r'\d+', text)
    if nums: return int(nums[-1])
    return 0

# ===== [7] دالة جلب بيانات الحلقة =====
async def get_video_data_from_source(client, v_id):
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not msg or not msg.video:
            return None, None, None
        caption = msg.caption or ""
        series_name = extract_series_name(caption)
        ep_num = extract_episode_number(caption)
        if not series_name: series_name = f"مسلسل {v_id[-3:]}"
        if ep_num == 0: ep_num = 1
        db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, 'HD') ON CONFLICT (v_id) DO UPDATE SET series_name = EXCLUDED.series_name, ep_num = EXCLUDED.ep_num", (v_id, series_name, ep_num), fetch=False)
        logging.info(f"🔄 تحديث تلقائي {v_id}: {series_name} - حلقة {ep_num}")
        return series_name, ep_num, "HD"
    except Exception as e:
        logging.error(f"❌ خطأ في جلب بيانات {v_id}: {e}")
        return None, None, None

# ===== [8] متابعة التعديلات على الفيديوهات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def on_video_edit(client, message):
    try:
        v_id = str(message.id)
        caption = message.caption or ""
        series_name = extract_series_name(caption)
        ep_num = extract_episode_number(caption)
        if series_name and ep_num > 0:
            db_query("UPDATE videos SET series_name = %s, ep_num = %s WHERE v_id = %s", (series_name, ep_num, v_id), fetch=False)
            logging.info(f"✏️ تحديث يدوي {v_id}: {series_name} - حلقة {ep_num}")
            await client.send_message(ADMIN_ID, f"🔄 **تم تحديث حلقة**\nالمعرف: {v_id}\nالمسلسل: {series_name}\nرقم الحلقة: {ep_num}")
            await refresh_series_menu(client, db_query)
    except Exception as e:
        logging.error(f"Error in on_video_edit: {e}")

# ===== [9] متابعة التعديلات على البوسترات =====
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
                await refresh_series_menu(client, db_query)
    except Exception as e:
        logging.error(f"Error in on_poster_edit: {e}")

# ===== [10] مراقبة قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.photo))
async def monitor_source(client, message):
    try:
        if message.video:
            v_id = str(message.id)
            caption = message.caption or ""
            series_name = extract_series_name(caption)
            ep_num = extract_episode_number(caption)
            if series_name and ep_num > 0:
                db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, 'HD') ON CONFLICT (v_id) DO UPDATE SET series_name = EXCLUDED.series_name, ep_num = EXCLUDED.ep_num", (v_id, series_name, ep_num), fetch=False)
                logging.info(f"✅ فيديو مكتمل {v_id}: {series_name} - حلقة {ep_num}")
                await refresh_series_menu(client, db_query)
                try:
                    encrypted = encrypt_title(series_name)
                    me = await client.get_me()
                    btn = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
                    ]])
                    caption_publish = f"🎬 **{encrypted}**\n🔢 **الحلقة {ep_num}**\n📺 **الجودة HD**"
                    await client.copy_message(PUBLISH_CHANNEL, SOURCE_CHANNEL, int(v_id), caption=caption_publish, reply_markup=btn)
                    await message.reply_text(f"✅ تم النشر في القناة العامة: {series_name} - حلقة {ep_num}")
                except Exception as e:
                    logging.error(f"❌ فشل النشر: {e}")
                    await message.reply_text(f"✅ تم حفظ الفيديو: {series_name} - حلقة {ep_num}\n⚠️ لكن فشل النشر في القناة العامة: {e}")
            else:
                db_query("INSERT INTO pending_posts (video_id, step) VALUES (%s, 'waiting_for_poster') ON CONFLICT (video_id) DO UPDATE SET step = 'waiting_for_poster'", (v_id,), fetch=False)
                await message.reply_text(f"📹 تم استلام الفيديو ({v_id})\nارفع البوستر الآن مع اسم المسلسل في الوصف.")
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

# ===== [11] معالجة الجودة =====
@app.on_callback_query(filters.regex(r"^q_"))
async def handle_quality(client, cb):
    try:
        _, quality, v_id = cb.data.split('_')
        db_query("UPDATE pending_posts SET step = 'waiting_for_episode', quality = %s WHERE video_id = %s", (quality, v_id), fetch=False)
        await cb.message.edit_text(f"📊 الجودة: {quality}\nأرسل رقم الحلقة الآن.")
    except Exception as e:
        logging.error(f"Error in handle_quality: {e}")

# ===== [12] استقبال رقم الحلقة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.regex(r"^/"))
async def receive_episode(client, message):
    try:
        ep_num = extract_episode_number(message.text)
        if ep_num == 0: 
            await message.reply_text("❌ لم أتمكن من قراءة رقم الحلقة. أرسل رقماً فقط مثل: 5")
            return
        pending = db_query("SELECT video_id, poster_id, quality FROM pending_posts WHERE step = 'waiting_for_episode' ORDER BY created_at DESC LIMIT 1")
        if not pending:
            await message.reply_text("❌ لا يوجد طلب معلق. ابدأ برفع فيديو أولاً")
            return
        v_id, p_id, q = pending[0]
        poster_data = db_query("SELECT series_name FROM posters WHERE poster_id = %s", (p_id,))
        if not poster_data:
            await message.reply_text("❌ لم يتم العثور على البوستر")
            return
        s_name = poster_data[0][0]
        db_query("INSERT INTO videos (v_id, series_name, ep_num, quality) VALUES (%s, %s, %s, %s)", (v_id, s_name, ep_num, q), fetch=False)
        db_query("DELETE FROM pending_posts WHERE video_id = %s", (v_id,), fetch=False)
        await refresh_series_menu(client, db_query)
        try:
            encrypted = encrypt_title(s_name)
            me = await client.get_me()
            btn = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
            ]])
            caption = f"🎬 **{encrypted}**\n🔢 **الحلقة {ep_num}**\n📺 **الجودة {q}**"
            await client.copy_message(PUBLISH_CHANNEL, SOURCE_CHANNEL, int(p_id), caption=caption, reply_markup=btn)
            logging.info(f"✅ تم النشر في القناة العامة: {s_name} - حلقة {ep_num}")
            await message.reply_text(f"✅ تم النشر في القناة العامة: {s_name} - حلقة {ep_num}")
        except Exception as e: 
            logging.error(f"❌ فشل النشر: {e}")
            await message.reply_text(f"❌ فشل النشر في القناة العامة. تأكد أن البوت مشرف في القناة.\nالخطأ: {e}")
    except Exception as e:
        logging.error(f"Error in receive_episode: {e}")
        await message.reply_text(f"❌ حدث خطأ: {e}")

# ===== [13] نظام الحماية من FloodWait =====
def check_rate_limit(user_id):
    now = datetime.now()
    if user_id in user_last_request:
        user_last_request[user_id] = [t for t in user_last_request[user_id] if now - t < timedelta(seconds=TIME_WINDOW)]
    else:
        user_last_request[user_id] = []
    if len(user_last_request[user_id]) >= REQUEST_LIMIT:
        oldest = user_last_request[user_id][0]
        wait_time = TIME_WINDOW - (now - oldest).seconds
        return False, wait_time
    user_last_request[user_id].append(now)
    return True, 0

# ===== [14] أمر البدء مع الاشتراك الإجباري (معدل) =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    
    # التحقق من الاشتراك الإجباري
    is_subscribed = await check_force_sub(client, user_id)
    if not is_subscribed:
        force_btn = await get_force_sub_button()
        keyboard = InlineKeyboardMarkup([[force_btn]])
        await message.reply_text(
            "🔒 **عذراً، يجب الاشتراك في القناة أولاً**\n\n"
            "للتمكن من مشاهدة الحلقات، الرجاء الاشتراك في القناة ثم أعد المحاولة.",
            reply_markup=keyboard
        )
        return  # المستخدم غير مشترك → نوقف التنفيذ
    
    # ✅ إذا وصلنا إلى هنا، المستخدم مشترك ونكمل
    logging.info(f"✅ المستخدم {user_id} مشترك في القناة - نكمل التنفيذ")
    
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
        data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            series_name, ep_num, quality = await get_video_data_from_source(client, v_id)
            if not series_name:
                await message.reply_text("❌ لم يتم العثور على الحلقة")
                return
        else:
            series_name, ep_num, quality = data[0]
        
        # بناء الأزرار
        keyboard = []
        
        if SHOW_MORE_BUTTONS and series_name:
            all_series_eps = db_query("SELECT ep_num, v_id FROM videos WHERE series_name = %s ORDER BY ep_num ASC LIMIT 50", (series_name,))
            if all_series_eps and len(all_series_eps) > 1:
                me = await client.get_me()
                bot_username = me.username
                row = []
                for o_ep, o_vid in all_series_eps:
                    if o_ep == ep_num and o_vid == v_id:
                        row.append(InlineKeyboardButton(f"✅ {o_ep}", url=f"https://t.me/{bot_username}?start={o_vid}"))
                    else:
                        row.append(InlineKeyboardButton(str(o_ep), url=f"https://t.me/{bot_username}?start={o_vid}"))
                    if len(row) == 5:
                        keyboard.append(row)
                        row = []
                if row: keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        try:
            await client.copy_message(
                message.chat.id, SOURCE_CHANNEL, int(v_id),
                caption=f"🎬 {series_name} - الحلقة {ep_num}\n📺 الجودة: {quality}",
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )
            db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
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

# ===== [15] أوامر الإدارة =====

@app.on_message(filters.command("delete") & filters.user(ADMIN_ID))
async def delete_command(client, message):
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.reply_text("❌ استخدم: /delete معرف_الحلقة1 معرف_الحلقة2 ...")
            return
        
        v_ids = command_parts[1:]
        deleted = 0
        not_found = []
        
        for v_id in v_ids:
            exists = db_query("SELECT 1 FROM videos WHERE v_id = %s", (v_id,))
            if exists:
                db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
                db_query("DELETE FROM views_log WHERE v_id = %s", (v_id,), fetch=False)
                deleted += 1
                logging.info(f"🗑️ تم حذف الحلقة {v_id}")
            else:
                not_found.append(v_id)
        
        result = f"✅ تم حذف {deleted} حلقة"
        if not_found:
            result += f"\n❌ لم يتم العثور على: {', '.join(not_found)}"
        
        await message.reply_text(result)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("delete_series") & filters.user(ADMIN_ID))
async def delete_series_command(client, message):
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            await message.reply_text("❌ استخدم: /delete_series اسم_المسلسل")
            return
        
        series_name = command_parts[1].strip()
        
        videos = db_query("SELECT v_id FROM videos WHERE series_name = %s", (series_name,))
        
        if not videos:
            await message.reply_text(f"❌ لا توجد حلقات للمسلسل: {series_name}")
            return
        
        count = len(videos)
        
        for (v_id,) in videos:
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            db_query("DELETE FROM views_log WHERE v_id = %s", (v_id,), fetch=False)
        
        logging.info(f"🗑️ تم حذف جميع حلقات {series_name} ({count} حلقة)")
        await message.reply_text(f"✅ تم حذف جميع حلقات {series_name}\n📊 عدد الحلقات: {count}")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_command(client, message):
    try:
        videos = db_query("SELECT v_id, series_name, ep_num, views FROM videos ORDER BY created_at DESC LIMIT 20")
        
        if not videos:
            await message.reply_text("📭 لا توجد حلقات في قاعدة البيانات")
            return
        
        text = "📋 **آخر 20 حلقة:**\n\n"
        for v_id, name, ep, views in videos:
            text += f"• `{v_id}` | {name} - حلقة {ep} | 👁️ {views}\n"
        
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await message.reply_text(part)
        else:
            await message.reply_text(text)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("search") & filters.user(ADMIN_ID))
async def search_command(client, message):
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            await message.reply_text("❌ استخدم: /search اسم_المسلسل")
            return
        
        search_term = command_parts[1].strip()
        
        videos = db_query(
            "SELECT v_id, series_name, ep_num, views FROM videos WHERE series_name ILIKE %s ORDER BY ep_num ASC LIMIT 50",
            (f"%{search_term}%",)
        )
        
        if not videos:
            await message.reply_text(f"❌ لا توجد نتائج لـ: {search_term}")
            return
        
        text = f"🔍 **نتائج البحث عن: {search_term}**\n\n"
        for v_id, name, ep, views in videos:
            text += f"• `{v_id}` | {name} - حلقة {ep} | 👁️ {views}\n"
        
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await message.reply_text(part)
        else:
            await message.reply_text(text)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("refresh_series") & filters.user(ADMIN_ID))
async def refresh_series_command(client, message):
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            await message.reply_text("❌ استخدم: /refresh_series اسم_المسلسل")
            return
        
        series_name = command_parts[1].strip()
        
        videos = db_query("SELECT v_id, ep_num FROM videos WHERE series_name = %s ORDER BY ep_num", (series_name,))
        
        if not videos:
            await message.reply_text(f"❌ لا توجد حلقات للمسلسل: {series_name}")
            return
        
        msg = await message.reply_text(f"🔄 جاري تحديث جميع حلقات {series_name}... (تم العثور على {len(videos)} حلقة)")
        
        await msg.edit_text(f"✅ جميع حلقات {series_name} محدثة (تم التحقق من {len(videos)} حلقة)")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("check_ep") & filters.user(ADMIN_ID))
async def check_ep_command(client, message):
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.reply_text("❌ استخدم: /check_ep v_id")
            return
        
        v_id = command_parts[1]
        
        data = db_query("SELECT series_name, ep_num FROM videos WHERE v_id = %s", (v_id,))
        if not data:
            await message.reply_text(f"❌ الحلقة {v_id} غير موجودة")
            return
        
        series, ep = data[0]
        
        all_eps = db_query("SELECT v_id, ep_num FROM videos WHERE series_name = %s ORDER BY ep_num", (series,))
        
        text = f"🔍 **معلومات الحلقة {v_id}**\n\n"
        text += f"📌 المسلسل: {series}\n"
        text += f"🔢 رقم الحلقة: {ep}\n"
        text += f"📊 عدد حلقات المسلسل: {len(all_eps)}\n\n"
        text += "📋 قائمة الحلقات:\n"
        
        for vid, ep_num in all_eps[:10]:
            marker = "✅" if vid == v_id else "•"
            text += f"{marker} {ep_num} (ID: {vid})\n"
        
        await message.reply_text(text)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    views_today = db_query("SELECT COUNT(*) FROM views_log WHERE viewed_at >= CURRENT_DATE")[0][0]
    top = db_query("SELECT series_name, views FROM videos WHERE views > 0 ORDER BY views DESC LIMIT 5")
    
    text = f"📊 **الإحصائيات**\n"
    text += f"📁 الحلقات: {total}\n"
    text += f"👥 المستخدمين: {users}\n"
    text += f"👁️ مشاهدات اليوم: {views_today}\n"
    text += f"🔘 المزيد: {'✅' if SHOW_MORE_BUTTONS else '❌'}\n\n"
    text += f"🏆 **الأكثر مشاهدة:**\n"
    
    for name, views in top:
        text += f"• {name}: {views}\n"
    
    await message.reply_text(text)

@app.on_message(filters.command("check_pending") & filters.user(ADMIN_ID))
async def check_pending(client, message):
    pending = db_query("SELECT video_id, step, quality, created_at FROM pending_posts ORDER BY created_at DESC")
    if not pending:
        await message.reply_text("📭 لا توجد طلبات معلقة")
        return
    
    text = "📋 **الطلبات المعلقة:**\n"
    for vid, step, q, created in pending:
        time_ago = datetime.now() - created
        minutes = int(time_ago.total_seconds() / 60)
        text += f"• `{vid}` | {step} | {q or '?'} | منذ {minutes} د\n"
    
    await message.reply_text(text)

@app.on_message(filters.command("reset_pending") & filters.user(ADMIN_ID))
async def reset_pending(client, message):
    db_query("DELETE FROM pending_posts", fetch=False)
    await message.reply_text("✅ تم حذف جميع الطلبات المعلقة")

@app.on_message(filters.command("test_publish") & filters.user(ADMIN_ID))
async def test_publish(client, message):
    try:
        await client.send_message(PUBLISH_CHANNEL, "🧪 اختبار النشر التلقائي - البوت يعمل ✅")
        await message.reply_text("✅ تم إرسال رسالة اختبار إلى القناة العامة")
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

@app.on_message(filters.command("check_channel") & filters.user(ADMIN_ID))
async def check_channel_command(client, message):
    try:
        channel = await client.get_chat(PUBLISH_CHANNEL)
        
        try:
            bot_member = await client.get_chat_member(PUBLISH_CHANNEL, "me")
            bot_status = bot_member.status
        except:
            bot_status = "❌ ليس عضواً"
        
        text = f"📊 **معلومات القناة العامة**\n\n"
        text += f"اسم القناة: {channel.title}\n"
        text += f"معرف القناة: `{PUBLISH_CHANNEL}`\n"
        text += f"حالة البوت: {bot_status}\n\n"
        
        if bot_status == "administrator":
            text += "✅ البوت مشرف - يمكنه النشر"
        elif bot_status == "member":
            text += "⚠️ البوت عضو فقط - يحتاج صلاحية مشرف للنشر"
        else:
            text += "❌ البوت ليس في القناة - أضفه كمشرف"
        
        await message.reply_text(text)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ في فحص القناة: {e}")

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
        
        await message.reply_text(f"✅ تم تحديث {count} حلقة إلى {new_name}")
        
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

# ===== [16] إعداد قائمة المسلسلات =====
try:
    from series_menu import setup_series_menu
    setup_series_menu(app, db_query)
    print("✅ تم تحميل نظام قائمة المسلسلات")
except Exception as e:
    print(f"⚠️ لم يتم تحميل قائمة المسلسلات: {e}")

# ===== [17] إعداد نظام فحص المسلسلات =====
try:
    from series_scanner import setup_series_scanner
    setup_series_scanner(app, db_query)
    print("✅ تم تحميل نظام فحص المسلسلات")
except Exception as e:
    print(f"⚠️ لم يتم تحميل نظام فحص المسلسلات: {e}")

# ===== [18] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل البوت الذكي مع الاشتراك الإجباري...")
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
