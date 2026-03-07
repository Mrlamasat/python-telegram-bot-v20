import os, psycopg2, logging, re, asyncio, time
from datetime import datetime
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
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

PUBLIC_CHANNELS = [
    -1003554018307,
    -1003790915936,
    -1003678294148,
    -1003690441303
]

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دوال قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

# ===== [3] استخراج رقم الحلقة بدقة =====
def extract_ep_num(text):
    if not text:
        return 0
    
    # تنظيف النص
    text = str(text)
    
    # قائمة بكل الطرق الممكنة لكتابة رقم الحلقة
    patterns = [
        # حلقة 1, حلقه 1, الحلقة 1, الحلقه 1
        r'(?:حلقه|حلقة|الحلقة|الحلقه|الحلقہ)\s*[:\-\s]*(?:الليلة)?\s*(\d+)',
        
        # رقم 1
        r'رقم\s*[:\-\s]*(\d+)',
        
        # ep 1, episode 1
        r'(?:ep|episode)\s*[:\-\s]*(\d+)',
        
        # #1
        r'#(\d+)',
        
        # [1]
        r'\[(\d+)\]',
        
        # (1)
        r'\((\d+)\)',
        
        # -1
        r'-(\d+)',
        
        # مجرد رقم في النص (آخر خيار)
        r'\b(\d+)\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return 0

# ===== [4] إنشاء جداول قاعدة البيانات =====
def init_database():
    # إنشاء جدول الفيديوهات
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            status TEXT DEFAULT 'posted',
            source_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # إنشاء جدول المستخدمين
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # إنشاء جدول المشاهدات
    db_query("""
        CREATE TABLE IF NOT EXISTS views_log (
            id SERIAL PRIMARY KEY,
            v_id TEXT,
            user_id BIGINT,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    print("✅ تم التأكد من وجود الجداول في قاعدة البيانات")

# ===== [5] أمر فحص وإصلاح قاعدة البيانات بالكامل =====
@app.on_message(filters.command("fix_all") & filters.user(ADMIN_ID))
async def fix_all_command(client, message):
    msg = await message.reply_text("🔍 جاري فحص وإصلاح جميع البيانات...")
    
    stats = {
        'total': 0,
        'fixed': 0,
        'skipped': 0,
        'errors': 0
    }
    
    # مسح جميع قنوات النشر
    for channel_id in PUBLIC_CHANNELS:
        try:
            await msg.edit_text(f"🔄 جاري فحص القناة {PUBLIC_CHANNELS.index(channel_id)+1}/4...")
            
            async for post in client.get_chat_history(channel_id, limit=1000):
                if post.reply_markup:
                    for row in post.reply_markup.inline_keyboard:
                        for btn in row:
                            if btn.url and "start=" in btn.url:
                                stats['total'] += 1
                                try:
                                    v_id = btn.url.split("start=")[1]
                                    
                                    # جلب الحلقة من قناة المصدر
                                    source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                                    
                                    if source_msg and (source_msg.caption or source_msg.text):
                                        raw_text = source_msg.caption or source_msg.text
                                        
                                        # استخراج العنوان ورقم الحلقة
                                        lines = raw_text.strip().split('\n')
                                        title = lines[0][:100] if lines else "فيديو"
                                        ep = extract_ep_num(raw_text)
                                        
                                        if ep > 0:
                                            # حفظ في قاعدة البيانات
                                            db_query("""
                                                INSERT INTO videos (v_id, title, ep_num, source_text, status) 
                                                VALUES (%s, %s, %s, %s, 'posted')
                                                ON CONFLICT (v_id) DO UPDATE SET 
                                                title = EXCLUDED.title,
                                                ep_num = EXCLUDED.ep_num,
                                                source_text = EXCLUDED.source_text
                                            """, (v_id, title, ep, raw_text[:500]), fetch=False)
                                            stats['fixed'] += 1
                                        else:
                                            stats['skipped'] += 1
                                    else:
                                        stats['skipped'] += 1
                                        
                                except Exception as e:
                                    stats['errors'] += 1
                                    logging.error(f"Error processing: {e}")
                                    
        except Exception as e:
            logging.error(f"Error in channel {channel_id}: {e}")
    
    # عرض النتائج
    result_text = f"""✅ **تم الانتهاء من الفحص والإصلاح**

📊 **الإحصائيات:**
• إجمالي الحلقات المكتشفة: {stats['total']}
• الحلقات التي تم إصلاحها: {stats['fixed']}
• الحلقات التي تم تخطيها: {stats['skipped']}
• الأخطاء: {stats['errors']}

🔍 **حالة قاعدة البيانات:**
• عدد الحلقات في قاعدة البيانات: {db_query('SELECT COUNT(*) FROM videos')[0][0]}
• عدد الحلقات بأرقام صحيحة: {db_query('SELECT COUNT(*) FROM videos WHERE ep_num > 0')[0][0]}
"""
    
    await msg.edit_text(result_text)

# ===== [6] أمر عرض إحصائيات قاعدة البيانات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_command(client, message):
    # إحصائيات عامة
    total_videos = db_query("SELECT COUNT(*) FROM videos")[0][0]
    videos_with_numbers = db_query("SELECT COUNT(*) FROM videos WHERE ep_num > 0")[0][0]
    videos_without_numbers = db_query("SELECT COUNT(*) FROM videos WHERE ep_num <= 0 OR ep_num IS NULL")[0][0]
    
    # أكثر 10 مسلسلات
    top_series = db_query("""
        SELECT title, COUNT(*) as eps, MAX(ep_num) as max_ep 
        FROM videos 
        WHERE ep_num > 0 
        GROUP BY title 
        ORDER BY eps DESC 
        LIMIT 10
    """)
    
    # آخر 10 حلقات مضافة
    recent = db_query("""
        SELECT v_id, title, ep_num, created_at 
        FROM videos 
        WHERE ep_num > 0 
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    
    text = f"""📊 **إحصائيات قاعدة البيانات**

**عام:**
• إجمالي الفيديوهات: {total_videos}
• فيديوهات بأرقام: {videos_with_numbers}
• فيديوهات بدون أرقام: {videos_without_numbers}

**أكثر المسلسلات:**
"""
    
    for title, count, max_ep in top_series:
        text += f"• {title}: {count} حلقة (آخرها {max_ep})\n"
    
    text += "\n**آخر الحلقات المضافة:**\n"
    for v_id, title, ep, date in recent:
        text += f"• {title} - حلقة {ep}\n"
    
    await message.reply_text(text)

# ===== [7] أمر تحديث حلقة معينة =====
@app.on_message(filters.command("update") & filters.user(ADMIN_ID))
async def update_episode(client, message):
    command = message.text.split()
    if len(command) < 2:
        return await message.reply_text("❌ الرجاء إرسال معرف الحلقة: /update 123456")
    
    v_id = command[1]
    
    msg = await message.reply_text(f"🔄 جاري تحديث الحلقة {v_id}...")
    
    try:
        # جلب من قناة المصدر
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        
        if not source_msg or not (source_msg.caption or source_msg.text):
            return await msg.edit_text("❌ لم يتم العثور على الحلقة في قناة المصدر")
        
        raw_text = source_msg.caption or source_msg.text
        title = raw_text.split('\n')[0][:100]
        ep = extract_ep_num(raw_text)
        
        if ep == 0:
            return await msg.edit_text("❌ لم يتم العثور على رقم الحلقة في النص")
        
        # تحديث قاعدة البيانات
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, source_text, status) 
            VALUES (%s, %s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num,
            source_text = EXCLUDED.source_text
        """, (v_id, title, ep, raw_text[:500]), fetch=False)
        
        await msg.edit_text(f"✅ تم تحديث الحلقة بنجاح!\n\nالعنوان: {title}\nرقم الحلقة: {ep}")
        
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {str(e)}")

# ===== [8] عرض الحلقة للمستخدم (الحل النهائي) =====
async def show_episode(client, message, v_id):
    try:
        # محاولة جلب البيانات من قاعدة البيانات أولاً
        db_data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        title = None
        ep = 0
        
        if db_data and len(db_data) > 0:
            title, ep = db_data[0]
        
        # جلب البيانات من قناة المصدر دائماً (للتأكد)
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        
        if not source_msg or not (source_msg.caption or source_msg.text):
            return await message.reply_text("❌ لم يتم العثور على الحلقة في قناة المصدر")
        
        raw_text = source_msg.caption or source_msg.text
        
        # استخراج العنوان إذا لم يكن موجوداً في قاعدة البيانات
        if not title:
            title = raw_text.split('\n')[0][:100]
        
        # استخراج رقم الحلقة (الأولوية للنص المباشر)
        extracted_ep = extract_ep_num(raw_text)
        if extracted_ep > 0:
            ep = extracted_ep  # استخدم الرقم المستخرج حديثاً
        
        # تحديث قاعدة البيانات بالرقم الصحيح
        if ep > 0:
            db_query("""
                INSERT INTO videos (v_id, title, ep_num, source_text, status) 
                VALUES (%s, %s, %s, %s, 'posted')
                ON CONFLICT (v_id) DO UPDATE SET 
                ep_num = EXCLUDED.ep_num,
                title = EXCLUDED.title
            """, (v_id, title, ep, raw_text[:500]), fetch=False)
        
        # جلب الحلقات الأخرى لنفس المسلسل
        other_eps = db_query("""
            SELECT ep_num, v_id FROM videos 
            WHERE title = %s AND status = 'posted' AND ep_num > 0 
            ORDER BY ep_num ASC
        """, (title,))
        
        # بناء لوحة المفاتيح
        keyboard = []
        
        if other_eps and len(other_eps) > 1:
            row = []
            me = await client.get_me()
            
            for o_ep, o_vid in other_eps:
                if str(o_vid) == str(v_id):
                    continue  # تخطي الحلقة الحالية
                
                row.append(InlineKeyboardButton(
                    str(o_ep), 
                    url=f"https://t.me/{me.username}?start={o_vid}"
                ))
                
                if len(row) == 5:
                    keyboard.append(row)
                    row = []
            
            if row:
                keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        # عرض رقم الحلقة (إذا كان 0 استخدم علامة استفهام)
        ep_display = ep if ep > 0 else "?"
        caption = f"<b>{title} - الحلقة {ep_display}</b>"
        
        # إرسال الحلقة
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
        
        # تسجيل المشاهدة
        db_query(
            "INSERT INTO views_log (v_id, user_id) VALUES (%s, %s)",
            (v_id, message.from_user.id),
            fetch=False
        )
        
        logging.info(f"✅ تم إرسال الحلقة {ep} للمستخدم {message.from_user.id}")
        
    except Exception as e:
        logging.error(f"❌ خطأ في show_episode: {e}")
        await message.reply_text("⚠️ حدث خطأ أثناء إرسال الحلقة")

# ===== [9] أمر البدء =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    # تسجيل المستخدم
    db_query(
        "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
        (message.from_user.id,),
        fetch=False
    )
    
    if len(message.command) > 1:
        # عرض الحلقة المطلوبة
        await show_episode(client, message, message.command[1])
    else:
        # رسالة الترحيب
        welcome_text = """👋 **أهلاً بك في بوت المشاهدة**

📺 **طريقة الاستخدام:**
• اضغط على أي حلقة من قنوات النشر
• سيظهر لك الفيديو مع أزرار الحلقات الأخرى

🔗 **قنوات النشر:**
• https://t.me/...
• https://t.me/...

🆘 **للتواصل مع المطور:** @Mohsen_7e
"""
        await message.reply_text(welcome_text)

# ===== [10] معالجة Flood Wait =====
async def handle_flood_wait(e):
    wait_time = e.value
    logging.warning(f"⚠️ Flood wait: {wait_time} seconds")
    print(f"⏳ الانتظار {wait_time} ثانية...")
    await asyncio.sleep(wait_time)
    return True

# ===== [11] التشغيل الرئيسي =====
def main():
    print("🚀 بدء تشغيل البوت...")
    print("✅ تهيئة قاعدة البيانات...")
    init_database()
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # حذف ملف الجلسة القديم
            session_file = "railway_final_pro.session"
            if os.path.exists(session_file):
                os.remove(session_file)
                print("✅ تم حذف ملف الجلسة القديم")
            
            print(f"📡 محاولة التشغيل {retry_count + 1}/{max_retries}")
            
            if not BOT_TOKEN:
                print("❌ خطأ: BOT_TOKEN غير موجود")
                return
            
            print("✅ تم التحقق من التوكن")
            print("🤖 تشغيل البوت...")
            
            app.run()
            break
            
        except FloodWait as e:
            retry_count += 1
            print(f"⚠️ Flood wait: {e.value} ثانية")
            
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(handle_flood_wait(e))
                loop.close()
            except:
                time.sleep(e.value)
                
        except Exception as e:
            retry_count += 1
            print(f"❌ خطأ: {type(e).__name__}: {e}")
            
            if retry_count < max_retries:
                wait = 30 * retry_count
                print(f"⏳ الانتظار {wait} ثانية...")
                time.sleep(wait)
    
    if retry_count >= max_retries:
        print("❌ فشل تشغيل البوت بعد 5 محاولات")
    else:
        print("✅ تم تشغيل البوت بنجاح!")

# ===== [12] نقطة الدخول =====
if __name__ == "__main__":
    main()
