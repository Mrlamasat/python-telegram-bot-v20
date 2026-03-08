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
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد"]

def encrypt_title(title):
    if not title: return "محتوى"
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
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, series_name TEXT, ep_num INTEGER DEFAULT 0, quality TEXT DEFAULT 'HD', views INTEGER DEFAULT 0)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS posters (poster_id BIGINT PRIMARY KEY, series_name TEXT, video_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT, first_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS pending_posts (video_id TEXT PRIMARY KEY, step TEXT, poster_id BIGINT, quality TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دوال الاستخراج =====
def extract_series_name(text):
    if not text: return None
    patterns = [r'^(.+?)\s+(?:حلقة|حلقه)\s+\d+$', r'^(.+?)\s+(\d+)$', r'^(.+?)\s*-\s*(\d+)$']
    for pattern in patterns:
        match = re.search(pattern, text.strip())
        if match: return match.group(1).strip()
    return text.strip()[:50]

def extract_episode_number(text):
    if not text: return 0
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 0

# ===== [6] دالة أزرار الحلقات الأخرى =====
def get_episode_buttons(series_name, current_id, bot_username):
    if not series_name: return []
    
    eps = db_query("SELECT ep_num, v_id FROM videos WHERE series_name = %s AND v_id != %s ORDER BY ep_num ASC LIMIT 30", (series_name, current_id))
    if not eps: return []
    
    keyboard, row = [], []
    for ep, vid in eps:
        row.append(InlineKeyboardButton(str(ep), url=f"https://t.me/{bot_username}?start={vid}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return keyboard

# ===== [7] متابعة التعديلات على الفيديوهات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def on_video_edit(client, message):
    v_id = str(message.id)
    new_series = extract_series_name(message.caption or "")
    new_ep = extract_episode_number(message.caption or "")
    if new_series and new_ep > 0:
        db_query("UPDATE videos SET series_name = %s, ep_num = %s WHERE v_id = %s", (new_series, new_ep, v_id), fetch=False)
        logging.info(f"✏️ تحديث فيديو {v_id}: {new_series} - حلقة {new_ep}")

# ===== [8] متابعة التعديلات على البوسترات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def on_poster_edit(client, message):
    poster_id = message.id
    new_series = extract_series_name(message.caption or "")
    if new_series:
        db_query("UPDATE posters SET series_name = %s WHERE poster_id = %s", (new_series, poster_id), fetch=False)
        video = db_query("SELECT video_id FROM posters WHERE poster_id = %s", (poster_id,))
        if video and video[0][0]:
            db_query("UPDATE videos SET series_name = %s WHERE v_id = %s", (new_series, video[0][0]), fetch=False)
            logging.info(f"✏️ تحديث بوستر {poster_id} → {new_series}")

# ===== [9] مراقبة قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.photo))
async def monitor_source(client, message):
    try:
        if message.video:
            v_id = str(message.id)
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
        logging.error(f"Error: {e}")

# ===== [10] معالجة الجودة =====
@app.on_callback_query(filters.regex(r"^q_"))
async def handle_quality(client, cb):
    _, quality, v_id = cb.data.split('_')
    db_query("UPDATE pending_posts SET step = 'waiting_for_episode', quality = %s WHERE video_id = %s", (quality, v_id), fetch=False)
    await cb.message.edit_text(f"📊 الجودة: {quality}\nأرسل رقم الحلقة الآن.")

# ===== [11] استقبال رقم الحلقة مع النشر التلقائي =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.regex(r"^/"))
async def receive_episode(client, message):
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

# ===== [12] أمر البدء مع أزرار المزيد من الحلقات (معدل مع علامة ✅) =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    # تسجيل المستخدم
    db_query("INSERT INTO users (user_id, username, first_name, last_used) VALUES (%s, %s, %s, CURRENT_TIMESTAMP) ON CONFLICT (user_id) DO UPDATE SET last_used = CURRENT_TIMESTAMP", 
             (message.from_user.id, message.from_user.username or "", message.from_user.first_name or ""), fetch=False)
    
    if len(message.command) > 1:
        v_id = message.command[1]
        data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            msg = await message.reply_text("🔄 جاري التحميل...")
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and source.video:
                    series = extract_series_name(source.caption or "") or f"مسلسل {v_id[-3:]}"
                    ep = extract_episode_number(source.caption or "") or 1
                    db_query("INSERT INTO videos (v_id, series_name, ep_num) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO NOTHING", (v_id, series, ep), fetch=False)
                    s_name, ep_num, quality = series, ep, "HD"
                else:
                    await msg.edit_text("❌ لم يتم العثور على الفيديو")
                    return
            except Exception as e:
                await msg.edit_text(f"❌ خطأ: {e}")
                return
        else:
            s_name, ep_num, quality = data[0]
        
        # بناء الأزرار مع تمييز الحلقة الحالية
        keyboard = []
        
        if SHOW_MORE_BUTTONS:
            # جلب الحلقات الأخرى
            other_eps = db_query("SELECT ep_num, v_id FROM videos WHERE series_name = %s AND v_id != %s ORDER BY ep_num ASC LIMIT 30", (s_name, v_id))
            
            if other_eps:
                row = []
                me = await client.get_me()
                bot_username = me.username
                
                # إضافة الحلقة الحالية أولاً مع علامة ✅
                row.append(InlineKeyboardButton(f"✅ {ep_num}", url=f"https://t.me/{bot_username}?start={v_id}"))
                
                # إضافة باقي الحلقات
                for o_ep, o_vid in other_eps:
                    row.append(InlineKeyboardButton(str(o_ep), url=f"https://t.me/{bot_username}?start={o_vid}"))
                    if len(row) == 5:
                        keyboard.append(row)
                        row = []
                
                if row:
                    keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        # إرسال الفيديو
        await client.copy_message(
            message.chat.id, SOURCE_CHANNEL, int(v_id),
            caption=f"🎬 {s_name} - الحلقة {ep_num}\n📺 الجودة: {quality}",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
        
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
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

# ===== [13] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    top = db_query("SELECT series_name, views FROM videos WHERE views > 0 ORDER BY views DESC LIMIT 5")
    
    text = f"📊 **الإحصائيات**\n📁 الحلقات: {total}\n👥 المستخدمين: {users}\n🔘 المزيد: {'✅' if SHOW_MORE_BUTTONS else '❌'}\n\n🏆 الأكثر مشاهدة:\n"
    for name, views in top:
        text += f"• {name}: {views}\n"
    
    await message.reply_text(text)

# ===== [14] أمر فحص الطلبات المعلقة =====
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

# ===== [15] أمر إعادة تعيين الطلبات المعلقة =====
@app.on_message(filters.command("reset_pending") & filters.user(ADMIN_ID))
async def reset_pending(client, message):
    db_query("DELETE FROM pending_posts", fetch=False)
    await message.reply_text("✅ تم حذف جميع الطلبات المعلقة")

# ===== [16] أمر اختبار النشر =====
@app.on_message(filters.command("test_publish") & filters.user(ADMIN_ID))
async def test_publish(client, message):
    try:
        await client.send_message(PUBLISH_CHANNEL, "🧪 اختبار النشر التلقائي")
        await message.reply_text("✅ تم إرسال رسالة اختبار")
    except Exception as e:
        await message.reply_text(f"❌ فشل الإرسال: {e}")

# ===== [17] أمر اختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [18] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل البوت المتكامل مع علامة ✅...")
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
