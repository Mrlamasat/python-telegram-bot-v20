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
    """تشفير اسم المسلسل للقناة فقط"""
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
            quality TEXT DEFAULT 'HD',
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    
    # جدول البوسترات
    db_query("""
        CREATE TABLE IF NOT EXISTS posters (
            poster_id INTEGER PRIMARY KEY,
            series_name TEXT,
            video_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # جدول المستخدمين
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # جدول الطلبات المعلقة
    db_query("""
        CREATE TABLE IF NOT EXISTS pending_posts (
            video_id TEXT PRIMARY KEY,
            step TEXT,
            poster_id INTEGER,
            quality TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دوال الاستخراج =====
def extract_series_name(text):
    """استخراج اسم المسلسل من النص"""
    if not text:
        return None
    
    patterns = [
        r'^(.+?)\s+(?:حلقة|حلقه)\s+\d+$',
        r'^(.+?)\s+(\d+)$',
        r'^(.+?)\s*-\s*(\d+)$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.strip())
        if match:
            return match.group(1).strip()
    
    return text.strip()[:50]

def extract_episode_number(text):
    """استخراج رقم الحلقة من النص"""
    if not text:
        return 0
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 0

def extract_series_from_video(text, v_id):
    """استخراج اسم المسلسل مع استخدام v_id كبديل"""
    series = extract_series_name(text)
    if not series:
        digits = re.sub(r'\D', '', v_id)
        suffix = digits[-3:] if len(digits) >= 3 else digits
        return f"مسلسل {suffix}"
    return series

# ===== [6] دالة أزرار الحلقات =====
def get_episode_buttons(series_name, current_id, bot_user):
    if not series_name:
        return []
    
    eps = db_query("""
        SELECT ep_num, v_id FROM videos 
        WHERE series_name = %s 
        ORDER BY ep_num ASC LIMIT 50
    """, (series_name,))
    
    if not eps or len(eps) < 2:
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

# ===== [7] متابعة التعديلات على الفيديوهات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def on_video_edit(client, message):
    if not message.video:
        return
    
    v_id = str(message.id)
    new_series = extract_series_name(message.caption or "")
    new_ep = extract_episode_number(message.caption or "")
    
    if new_series and new_ep > 0:
        db_query("""
            UPDATE videos 
            SET series_name = %s, ep_num = %s 
            WHERE v_id = %s
        """, (new_series, new_ep, v_id), fetch=False)
        logging.info(f"✏️ تحديث فيديو {v_id}: {new_series} - حلقة {new_ep}")

# ===== [8] متابعة التعديلات على البوسترات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def on_poster_edit(client, message):
    if not message.photo:
        return
    
    poster_id = message.id
    new_series = extract_series_name(message.caption or "")
    
    if new_series:
        db_query("""
            UPDATE posters 
            SET series_name = %s 
            WHERE poster_id = %s
        """, (new_series, poster_id), fetch=False)
        
        video = db_query("SELECT video_id FROM posters WHERE poster_id = %s", (poster_id,))
        if video and video[0][0]:
            video_id = video[0][0]
            db_query("""
                UPDATE videos 
                SET series_name = %s 
                WHERE v_id = %s
            """, (new_series, video_id), fetch=False)
            logging.info(f"✏️ تحديث بوستر {poster_id} → {new_series} (مرتبط بالفيديو {video_id})")

# ===== [9] مراقبة قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def monitor_source(client, message):
    try:
        if message.video:
            v_id = str(message.id)
            logging.info(f"📹 تم استلام فيديو: {v_id}")
            
            try:
                db_query("""
                    INSERT INTO pending_posts (video_id, step) 
                    VALUES (%s, 'waiting_for_poster')
                    ON CONFLICT (video_id) DO UPDATE SET step = 'waiting_for_poster'
                """, (v_id,), fetch=False)
                
                await client.send_message(
                    SOURCE_CHANNEL,
                    f"📹 **تم استلام الفيديو**\nالمعرف: {v_id}\nالرجاء رفع البوستر الآن"
                )
                logging.info(f"✅ تم تسجيل الفيديو {v_id} في pending_posts")
            except Exception as e:
                logging.error(f"❌ فشل تسجيل الفيديو {v_id}: {e}")
            return
        
        elif message.photo:
            poster_id = message.id
            series_name = extract_series_name(message.caption or "")
            logging.info(f"🖼 تم استلام بوستر: {poster_id} باسم {series_name}")
            
            if not series_name:
                await client.send_message(
                    SOURCE_CHANNEL,
                    "⚠️ الرجاء كتابة اسم المسلسل في وصف البوستر"
                )
                return
            
            pending = db_query("""
                SELECT video_id FROM pending_posts 
                WHERE step = 'waiting_for_poster' 
                ORDER BY created_at DESC LIMIT 1
            """)
            
            if pending:
                video_id = pending[0][0]
                
                db_query("""
                    INSERT INTO posters (poster_id, series_name, video_id) 
                    VALUES (%s, %s, %s)
                """, (poster_id, series_name, video_id), fetch=False)
                
                db_query("""
                    UPDATE pending_posts 
                    SET step = 'waiting_for_quality', poster_id = %s 
                    WHERE video_id = %s
                """, (poster_id, video_id), fetch=False)
                
                quality_keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("HD", callback_data=f"quality_HD_{video_id}"),
                        InlineKeyboardButton("SD", callback_data=f"quality_SD_{video_id}"),
                        InlineKeyboardButton("4K", callback_data=f"quality_4K_{video_id}")
                    ]
                ])
                
                await client.send_message(
                    SOURCE_CHANNEL,
                    f"🖼 **تم ربط البوستر**\nالمسلسل: {series_name}\nاختر جودة الفيديو:",
                    reply_markup=quality_keyboard
                )
                logging.info(f"🖼 بوستر {poster_id} مرتبط بالفيديو {video_id}")
            else:
                await client.send_message(
                    SOURCE_CHANNEL,
                    "⚠️ لا يوجد فيديو في انتظار البوستر. الرجاء رفع الفيديو أولاً."
                )
    except Exception as e:
        logging.error(f"❌ خطأ عام في monitor_source: {e}")

# ===== [10] معالجة أزرار الجودة =====
@app.on_callback_query()
async def handle_quality(client, callback_query):
    data = callback_query.data.split('_')
    if len(data) < 3 or data[0] != 'quality':
        return
    
    quality = data[1]
    video_id = data[2]
    
    db_query("""
        UPDATE pending_posts 
        SET step = 'waiting_for_episode', quality = %s 
        WHERE video_id = %s
    """, (quality, video_id), fetch=False)
    
    await callback_query.message.edit_text(
        f"📊 **تم اختيار الجودة:** {quality}\n"
        f"الرجاء إرسال رقم الحلقة الآن"
    )
    await callback_query.answer()
    logging.info(f"✅ تم اختيار الجودة {quality} للفيديو {video_id}")

# ===== [11] استقبال رقم الحلقة (نسخة مع تسجيل تفصيلي) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text)
async def receive_episode(client, message):
    # تسجيل وصول أي رسالة نصية
    logging.info(f"📝 رسالة نصية واردة: {message.text}")
    
    # استخراج الرقم من الرسالة
    ep_num = extract_episode_number(message.text)
    
    # إذا لم تكن الرسالة رقماً، نسجل ونتجاهل
    if ep_num == 0:
        logging.info(f"⏭️ تم تجاهل الرسالة (لا تحتوي على رقم): {message.text}")
        return

    logging.info(f"🔢 تم استخراج الرقم: {ep_num}")

    # البحث عن آخر فيديو في انتظار رقم الحلقة
    pending = db_query("""
        SELECT video_id, poster_id, quality FROM pending_posts 
        WHERE step = 'waiting_for_episode' 
        ORDER BY created_at DESC LIMIT 1
    """)
    
    if not pending:
        logging.warning("⚠️ لا يوجد طلب في انتظار رقم الحلقة")
        await message.reply_text("⚠️ لا يوجد طلب في انتظار رقم الحلقة")
        return

    video_id, poster_id, quality = pending[0]
    logging.info(f"✅ وجدنا طلب معلق: video_id={video_id}, poster_id={poster_id}, quality={quality}")
    
    # جلب اسم المسلسل
    poster_data = db_query("SELECT series_name FROM posters WHERE poster_id = %s", (poster_id,))
    if not poster_data:
        logging.error(f"❌ لا يوجد بوستر بالمعرف {poster_id}")
        await message.reply_text(f"❌ خطأ: لم يتم العثور على البوستر رقم {poster_id}")
        return
    
    series_name = poster_data[0][0]
    logging.info(f"📛 اسم المسلسل: {series_name}")
    
    # حفظ في قاعدة البيانات
    try:
        db_query("""
            INSERT INTO videos (v_id, series_name, ep_num, quality) 
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (v_id) DO UPDATE SET 
            series_name = EXCLUDED.series_name,
            ep_num = EXCLUDED.ep_num,
            quality = EXCLUDED.quality
        """, (video_id, series_name, ep_num, quality), fetch=False)
        logging.info(f"💾 تم حفظ الفيديو {video_id} في قاعدة البيانات")
    except Exception as e:
        logging.error(f"❌ فشل حفظ الفيديو: {e}")
        await message.reply_text(f"❌ خطأ في حفظ البيانات: {e}")
        return
    
    # حذف الطلب المعلق
    db_query("DELETE FROM pending_posts WHERE video_id = %s", (video_id,), fetch=False)
    logging.info(f"🗑️ تم حذف الطلب المعلق {video_id}")
    
    # رسالة تأكيد
    await message.reply_text(f"✅ تم حفظ الحلقة:\n🎬 {series_name}\n🔢 {ep_num}\n📊 {quality}")
    logging.info(f"✅ تم إرسال رسالة التأكيد")

    # النشر التلقائي في قناة النشر
    try:
        encrypted = encrypt_title(series_name)
        me = await client.get_me()
        bot_link = f"https://t.me/{me.username}?start={video_id}"
        
        button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 مشاهدة الحلقة", url=bot_link)
        ]])

        caption = f"🎬 {encrypted}\n🔢 الحلقة {ep_num}\n📺 {quality}"
        
        logging.info(f"📤 جاري النشر في قناة {PUBLISH_CHANNEL}")

        await client.copy_message(
            chat_id=PUBLISH_CHANNEL,
            from_chat_id=SOURCE_CHANNEL,
            message_id=poster_id,
            caption=caption,
            reply_markup=button
        )
        logging.info(f"✅ تم النشر التلقائي للحلقة {ep_num} من {series_name}")
        
    except Exception as e:
        logging.error(f"❌ خطأ في النشر التلقائي: {e}")
        await message.reply_text(f"⚠️ تم حفظ الحلقة لكن فشل النشر التلقائي: {e}")

# ===== [12] أمر البدء =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("""
        INSERT INTO users (user_id, username, first_name, joined_at, last_used) 
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET last_used = CURRENT_TIMESTAMP
    """, (message.from_user.id, message.from_user.username or "", message.from_user.first_name or ""), fetch=False)
    
    if len(message.command) > 1:
        v_id = message.command[1]
        me = await client.get_me()
        
        data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            msg = await message.reply_text("🔄 جاري التحميل لأول مرة...")
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and source.video:
                    series = extract_series_from_video(source.caption or "", v_id)
                    ep = extract_episode_number(source.caption or "")
                    if ep == 0:
                        ep = 1
                    
                    db_query("""
                        INSERT INTO videos (v_id, series_name, ep_num) 
                        VALUES (%s, %s, %s)
                        ON CONFLICT (v_id) DO NOTHING
                    """, (v_id, series, ep), fetch=False)
                    
                    await msg.delete()
                    current_series, current_ep = series, ep
                    current_quality = "HD"
                else:
                    await msg.edit_text("❌ لم يتم العثور على الفيديو")
                    return
            except Exception as e:
                await msg.edit_text(f"❌ خطأ: {e}")
                return
        else:
            current_series, current_ep, current_quality = data[0]

        keyboard = []
        if SHOW_MORE_BUTTONS:
            more_buttons = get_episode_buttons(current_series, v_id, me.username)
            if more_buttons:
                keyboard.extend(more_buttons)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        caption = f"<b>🎬 {current_series} - الحلقة {current_ep}</b>"
        if current_quality:
            caption += f"\n📺 الجودة: {current_quality}"
        
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
        
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        welcome_text = """👋 **بوت المشاهدة الذكي**

📺 **طريقة الرفع في قناة المصدر:**
1️⃣ ارفع الفيديو (بدون وصف)
2️⃣ ارفع البوستر مع اسم المسلسل
3️⃣ اختر الجودة من الأزرار
4️⃣ أرسل رقم الحلقة

✅ **النشر التلقائي** سيتم بعد إرسال رقم الحلقة

🆘 @Mohsen_7e"""
        await message.reply_text(welcome_text)

# ===== [13] أمر النشر اليدوي =====
@app.on_message(filters.command("publish") & filters.user(ADMIN_ID))
async def publish_cmd(client, message):
    cmd = message.text.split()
    if len(cmd) < 2:
        await message.reply_text("❌ استخدم: /publish v_id")
        return
    
    v_id = cmd[1]
    
    try:
        data = db_query("SELECT series_name, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        if not data:
            await message.reply_text("❌ الحلقة غير موجودة في قاعدة البيانات")
            return
        
        series_name, ep, quality = data[0]
        encrypted = encrypt_title(series_name)
        
        poster = db_query("SELECT poster_id FROM posters WHERE video_id = %s", (v_id,))
        
        me = await client.get_me()
        bot_link = f"https://t.me/{me.username}?start={v_id}"
        
        button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 مشاهدة الحلقة", url=bot_link)
        ]])
        
        if poster and poster[0][0]:
            poster_id = poster[0][0]
            await client.copy_message(
                PUBLISH_CHANNEL,
                SOURCE_CHANNEL,
                poster_id,
                caption=f"{encrypted}\nالحلقة {ep}\n{quality}",
                reply_markup=button
            )
        else:
            await client.send_message(
                PUBLISH_CHANNEL,
                f"{encrypted}\nالحلقة {ep}\n{quality}",
                reply_markup=button
            )
        
        await message.reply_text(f"✅ تم النشر: {encrypted} - حلقة {ep} ({quality})")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [14] أمر الإحصائيات =====
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

# ===== [15] أمر فحص الطلبات المعلقة =====
@app.on_message(filters.command("check_pending") & filters.user(ADMIN_ID))
async def check_pending(client, message):
    pending = db_query("SELECT video_id, step, quality, created_at FROM pending_posts ORDER BY created_at DESC")
    
    if not pending:
        await message.reply_text("📭 لا توجد طلبات معلقة حالياً")
        return
    
    text = "📋 **الطلبات المعلقة:**\n\n"
    for vid, step, quality, date in pending:
        text += f"• {vid} | {step} | {quality or '?'} | {date}\n"
    
    await message.reply_text(text)

# ===== [16] أمر إعادة تعيين الطلبات المعلقة =====
@app.on_message(filters.command("reset_pending") & filters.user(ADMIN_ID))
async def reset_pending(client, message):
    db_query("DELETE FROM pending_posts", fetch=False)
    await message.reply_text("✅ تم حذف جميع الطلبات المعلقة")

# ===== [17] أمر اختبار النشر =====
@app.on_message(filters.command("test_publish") & filters.user(ADMIN_ID))
async def test_publish(client, message):
    try:
        await client.send_message(
            PUBLISH_CHANNEL,
            "🧪 هذا اختبار للنشر التلقائي"
        )
        await message.reply_text("✅ تم إرسال رسالة اختبار إلى قناة النشر")
    except Exception as e:
        await message.reply_text(f"❌ فشل الإرسال: {e}")

# ===== [18] أمر اختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [19] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل البوت الذكي مع النشر التلقائي...")
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
