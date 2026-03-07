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

# ===== [1.1] متغير التحكم بالأزرار =====
SHOW_MORE_BUTTONS = False  # False = إيقاف الأزرار, True = تشغيل الأزرار

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

# ===== [3] دالة استخراج رقم الحلقة البسيطة =====
def extract_ep_num_simple(text):
    """دالة بسيطة لاستخراج رقم الحلقة"""
    if not text:
        return 0
    patterns = [
        r'(?:حلقه|حلقة|الحلقة|الحلقه)\s*[:\-\s]*(\d+)',
        r'رقم\s*[:\-\s]*(\d+)',
        r'#(\d+)',
        r'\[(\d+)\]',
        r'\((\d+)\)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0

# ===== [4] دالة استخراج اسم المسلسل من النص =====
def extract_title(text):
    """تستخرج اسم المسلسل من النص (السطر الأول)"""
    if not text:
        return "فيديو"
    return text.strip().split('\n')[0][:100]

# ===== [5] دالة متطورة للبحث عن رقم الحلقة في جميع القنوات =====
async def find_episode_number(client, v_id):
    """
    تبحث عن رقم الحلقة في:
    1. وصف قناة المصدر
    2. قنوات النشر الأربعة (حيث يظهر الرقم قبل الضغط)
    """
    try:
        # أولاً: البحث في قناة المصدر
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if source_msg and (source_msg.caption or source_msg.text):
            text = source_msg.caption or source_msg.text
            ep = extract_ep_num_simple(text)
            if ep > 0:
                logging.info(f"✅ وجدنا رقم {ep} في قناة المصدر")
                return ep
        
        # ثانياً: البحث في قنوات النشر الأربعة
        logging.info("🔍 لم نجد في المصدر، نبحث في قنوات النشر...")
        
        for channel_id in PUBLIC_CHANNELS:
            try:
                # البحث عن الرسالة التي تحتوي على زر لهذا المعرف
                async for post in client.get_chat_history(channel_id, limit=200):
                    if not post.reply_markup:
                        continue
                    
                    for row in post.reply_markup.inline_keyboard:
                        for btn in row:
                            if btn.url and f"start={v_id}" in btn.url:
                                # وجدنا الزر، الآن نبحث عن رقم الحلقة في نفس الرسالة
                                if post.caption or post.text:
                                    text = post.caption or post.text
                                    ep = extract_ep_num_simple(text)
                                    if ep > 0:
                                        logging.info(f"✅ وجدنا رقم {ep} في قناة النشر {channel_id}")
                                        return ep
                                    
                                    # إذا لم نجد في الكابشن، نبحث في رسالة الرد
                                    if post.reply_to_message and (post.reply_to_message.caption or post.reply_to_message.text):
                                        reply_text = post.reply_to_message.caption or post.reply_to_message.text
                                        ep = extract_ep_num_simple(reply_text)
                                        if ep > 0:
                                            logging.info(f"✅ وجدنا رقم {ep} في رد قناة النشر")
                                            return ep
            except Exception as e:
                logging.error(f"خطأ في البحث في القناة {channel_id}: {e}")
                continue
        
        # ثالثاً: إذا لم نجد، نستخدم معرف الرسالة كرقم تقريبي
        try:
            # استخدام آخر رقمين من المعرف كرقم تقريبي
            approx_num = int(str(v_id)[-2:])  # آخر رقمين
            if approx_num == 0:
                approx_num = 1
            logging.info(f"⚠️ لم نجد رقم، نستخدم رقم تقريبي: {approx_num}")
            return approx_num
        except:
            return 1  # قيمة افتراضية
        
    except Exception as e:
        logging.error(f"خطأ في find_episode_number: {e}")
        return 1

# ===== [6] دالة عرض الحلقة (معدلة مع متغير التحكم) =====
async def show_episode(client, message, v_id):
    try:
        # جلب البيانات من قاعدة البيانات
        db_data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            return await message.reply_text("❌ حدث خطأ غير متوقع")
        
        title, ep = db_data[0]
        
        # بناء لوحة المفاتيح
        keyboard = []
        
        # فقط إذا كانت الأزرار مفعلة، نضيف أزرار الحلقات الأخرى
        if SHOW_MORE_BUTTONS:
            other_eps = db_query("""
                SELECT ep_num, v_id FROM videos 
                WHERE title = %s AND ep_num > 0 AND v_id != %s
                ORDER BY ep_num ASC
            """, (title, v_id))
            
            if other_eps:
                row = []
                me = await client.get_me()
                for o_ep, o_vid in other_eps:
                    row.append(InlineKeyboardButton(
                        str(o_ep), 
                        url=f"https://t.me/{me.username}?start={o_vid}"
                    ))
                    if len(row) == 5:
                        keyboard.append(row)
                        row = []
                if row:
                    keyboard.append(row)
        
        # زر القناة الاحتياطية يبقى دائمًا
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        # إرسال الحلقة
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=f"<b>{title} - الحلقة {ep}</b>",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
        
        # تسجيل المشاهدة
        db_query(
            "INSERT INTO views_log (v_id, user_id) VALUES (%s, %s)",
            (v_id, message.from_user.id),
            fetch=False
        )
        
    except Exception as e:
        logging.error(f"خطأ في show_episode: {e}")
        await message.reply_text("⚠️ حدث خطأ أثناء إرسال الحلقة")

# ===== [7] أمر البدء الذكي (معدل بالكامل) =====
@app.on_message(filters.command("start") & filters.private)
async def smart_start(client, message):
    # تسجيل المستخدم
    db_query(
        "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
        (message.from_user.id,),
        fetch=False
    )
    
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # التحقق من وجود الحلقة في قاعدة البيانات
        db_data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            # الحلقة غير موجودة → نجلبها ونصلحها تلقائياً
            waiting_msg = await message.reply_text("🔄 جاري تحضير الحلقة لأول مرة...")
            
            try:
                # جلب من قناة المصدر
                source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                
                if source_msg and (source_msg.caption or source_msg.text):
                    raw_text = source_msg.caption or source_msg.text
                    
                    # استخراج اسم المسلسل من المصدر
                    title = extract_title(raw_text)
                    
                    # البحث عن رقم الحلقة في جميع القنوات
                    ep_num = await find_episode_number(client, v_id)
                    
                    # حفظ في قاعدة البيانات
                    db_query("""
                        INSERT INTO videos (v_id, title, ep_num, status) 
                        VALUES (%s, %s, %s, 'posted')
                        ON CONFLICT (v_id) DO UPDATE SET 
                        title = EXCLUDED.title,
                        ep_num = EXCLUDED.ep_num
                    """, (v_id, title, ep_num), fetch=False)
                    
                    # إعلام المشرف
                    await client.send_message(
                        ADMIN_ID,
                        f"✅ **تم إصلاح حلقة جديدة تلقائياً!**\n"
                        f"المعرف: `{v_id}`\n"
                        f"المسلسل: {title}\n"
                        f"رقم الحلقة: {ep_num}"
                    )
                    
                    await waiting_msg.delete()
                    # الآن نعرض الحلقة
                    await show_episode(client, message, v_id)
                else:
                    await waiting_msg.edit_text("❌ لم يتم العثور على الحلقة في قناة المصدر")
                    
            except Exception as e:
                await waiting_msg.edit_text(f"❌ خطأ في تحضير الحلقة: {e}")
        else:
            # الحلقة موجودة → نعرضها مباشرة
            await show_episode(client, message, v_id)
    else:
        # رسالة الترحيب
        welcome_text = """👋 **أهلاً بك في بوت المشاهدة الذكي**

📺 **ميزة ذكية:** 
عندما تضغط على أي رابط لأول مرة، سيتم حفظه تلقائياً في قاعدة البيانات للمستقبل!

🆘 **للتواصل مع المطور:** @Mohsen_7e
"""
        await message.reply_text(welcome_text)

# ===== [8] أمر التحكم في أزرار المزيد من الحلقات =====
@app.on_message(filters.command("toggle_buttons") & filters.user(ADMIN_ID))
async def toggle_buttons(client, message):
    global SHOW_MORE_BUTTONS
    SHOW_MORE_BUTTONS = not SHOW_MORE_BUTTONS
    status = "✅ مفعلة" if SHOW_MORE_BUTTONS else "❌ معطلة"
    await message.reply_text(f"أزرار المزيد من الحلقات: {status}")

# ===== [9] أمر مسح قناة المصدر وتحديث جميع الحلقات =====
@app.on_message(filters.command("scan_source") & filters.user(ADMIN_ID))
async def scan_source_command(client, message):
    msg = await message.reply_text("🔄 جاري فحص قناة المصدر بالكامل...")
    
    stats = {
        'scanned': 0,
        'updated': 0,
        'errors': 0
    }
    
    # فحص آخر 500 رسالة في قناة المصدر
    async for post in client.get_chat_history(SOURCE_CHANNEL, limit=500):
        stats['scanned'] += 1
        
        try:
            if not (post.caption or post.text):
                continue
                
            raw_text = post.caption or post.text
            v_id = str(post.id)
            
            # استخراج اسم المسلسل
            title = extract_title(raw_text)
            
            # البحث عن رقم الحلقة في جميع القنوات
            ep_num = await find_episode_number(client, v_id)
            
            # تحديث قاعدة البيانات
            db_query("""
                INSERT INTO videos (v_id, title, ep_num, status) 
                VALUES (%s, %s, %s, 'posted')
                ON CONFLICT (v_id) DO UPDATE SET 
                title = EXCLUDED.title,
                ep_num = EXCLUDED.ep_num
            """, (v_id, title, ep_num), fetch=False)
            
            stats['updated'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            logging.error(f"خطأ: {e}")
        
        # تحديث كل 50 رسالة
        if stats['updated'] % 50 == 0 and stats['updated'] > 0:
            await msg.edit_text(f"🔄 تم تحديث {stats['updated']} حلقة...")
    
    # إحصائيات بعد الانتهاء
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    result = f"""✅ **تم فحص قناة المصدر**

📊 **الإحصائيات:**
• رسائل ممسوحة: {stats['scanned']}
• حلقات محدثة: {stats['updated']}
• أخطاء: {stats['errors']}

📁 **إجمالي الحلقات في قاعدة البيانات:** {total}

🔘 **حالة أزرار المزيد:** {"مفعلة" if SHOW_MORE_BUTTONS else "معطلة"}
"""
    await msg.edit_text(result)

# ===== [10] أمر إضافة حلقة جديدة يدوياً =====
@app.on_message(filters.command("add") & filters.user(ADMIN_ID))
async def add_episode(client, message):
    command = message.text.split()
    if len(command) < 3:
        return await message.reply_text("❌ استخدم: /add المعرف رقم_الحلقة اسم_المسلسل\nمثال: /add 3514 3 المداح")
    
    v_id = command[1]
    ep_num = int(command[2])
    title = ' '.join(command[3:])
    
    try:
        # التحقق من وجود الحلقة في قناة المصدر
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not source_msg:
            return await message.reply_text("❌ الحلقة غير موجودة في قناة المصدر")
        
        # حفظ في قاعدة البيانات
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status) 
            VALUES (%s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num
        """, (v_id, title, ep_num), fetch=False)
        
        await message.reply_text(f"✅ تم إضافة الحلقة\nالمسلسل: {title}\nرقم الحلقة: {ep_num}")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [11] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def smart_stats(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    
    # أكثر 10 مسلسلات
    top_series = db_query("""
        SELECT title, COUNT(*) as eps 
        FROM videos 
        GROUP BY title 
        ORDER BY eps DESC 
        LIMIT 10
    """)
    
    # آخر 5 حلقات مضافة
    recent = db_query("""
        SELECT v_id, title, ep_num, created_at 
        FROM videos 
        ORDER BY created_at DESC 
        LIMIT 5
    """)
    
    text = f"🤖 **إحصائيات البوت الذكي**\n\n"
    text += f"📁 إجمالي الحلقات: {total}\n"
    text += f"🔘 أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}\n\n"
    text += "📊 **أكثر 10 مسلسلات:**\n"
    
    for title, count in top_series:
        text += f"• {title}: {count} حلقة\n"
    
    text += "\n🆕 **آخر 5 حلقات مضافة:**\n"
    for v_id, title, ep, date in recent:
        short_id = v_id[:10] + "..." if len(v_id) > 10 else v_id
        text += f"• {title} - حلقة {ep} (ID: {short_id})\n"
    
    await message.reply_text(text)

# ===== [12] أمر الإصلاح السريع =====
@app.on_message(filters.command("fix") & filters.user(ADMIN_ID))
async def quick_fix(client, message):
    command = message.text.split()
    if len(command) < 2:
        return await message.reply_text("❌ استخدم: /fix 3514")
    
    v_id = command[1]
    
    try:
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not source_msg:
            return await message.reply_text("❌ الحلقة غير موجودة في قناة المصدر")
        
        raw_text = source_msg.caption or source_msg.text or ""
        
        # استخراج اسم المسلسل
        title = extract_title(raw_text)
        
        # البحث عن رقم الحلقة في جميع القنوات
        ep_num = await find_episode_number(client, v_id)
        
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status) 
            VALUES (%s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num
        """, (v_id, title, ep_num), fetch=False)
        
        await message.reply_text(f"✅ تم إصلاح الحلقة {v_id}\nالمسلسل: {title}\nرقم الحلقة: {ep_num}")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [13] أمر مزامنة قنوات النشر =====
@app.on_message(filters.command("sync") & filters.user(ADMIN_ID))
async def sync_all_channels(client, message):
    msg = await message.reply_text("🔄 جاري مزامنة جميع القنوات...")
    
    stats = {
        'total': 0,
        'added': 0,
        'errors': 0
    }
    
    for idx, channel_id in enumerate(PUBLIC_CHANNELS, 1):
        try:
            await msg.edit_text(f"📡 فحص القناة {idx}/4...")
            
            async for post in client.get_chat_history(channel_id, limit=200):
                if not post.reply_markup:
                    continue
                    
                for row in post.reply_markup.inline_keyboard:
                    for btn in row:
                        if btn.url and "start=" in btn.url:
                            stats['total'] += 1
                            try:
                                v_id = btn.url.split("start=")[1]
                                
                                # التحقق من وجودها في قاعدة البيانات
                                exists = db_query("SELECT 1 FROM videos WHERE v_id = %s", (v_id,))
                                if not exists:
                                    source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                                    if source_msg and (source_msg.caption or source_msg.text):
                                        raw_text = source_msg.caption or source_msg.text
                                        title = extract_title(raw_text)
                                        ep_num = await find_episode_number(client, v_id)
                                        
                                        db_query("""
                                            INSERT INTO videos (v_id, title, ep_num, status) 
                                            VALUES (%s, %s, %s, 'posted')
                                        """, (v_id, title, ep_num), fetch=False)
                                        stats['added'] += 1
                                        
                            except Exception as e:
                                stats['errors'] += 1
                                
        except Exception as e:
            continue
    
    total = db_query('SELECT COUNT(*) FROM videos')[0][0]
    await msg.edit_text(f"""✅ **تمت المزامنة**

📊 الإحصائيات:
• روابط مكتشفة: {stats['total']}
• حلقات جديدة: {stats['added']}
• أخطاء: {stats['errors']}

📁 إجمالي الحلقات: {total}
🔘 أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}""")

# ===== [14] أمر مسح قاعدة البيانات =====
@app.on_message(filters.command("reset") & filters.user(ADMIN_ID))
async def reset_database(client, message):
    confirm = await message.reply_text("⚠️ هل أنت متأكد؟ هذا سيمسح جميع البيانات!\nأرسل /reset_confirm لتأكيد")

@app.on_message(filters.command("reset_confirm") & filters.user(ADMIN_ID))
async def reset_confirm(client, message):
    db_query("DELETE FROM videos", fetch=False)
    db_query("DELETE FROM views_log", fetch=False)
    await message.reply_text("✅ تم مسح جميع البيانات")

# ===== [15] إنشاء الجداول تلقائياً =====
def init_database():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            status TEXT DEFAULT 'posted',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS views_log (
            id SERIAL PRIMARY KEY,
            v_id TEXT,
            user_id BIGINT,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    print("✅ تم التأكد من وجود الجداول في قاعدة البيانات")

# ===== [16] معالجة Flood Wait =====
async def handle_flood_wait(e):
    wait_time = e.value
    logging.warning(f"⚠️ Flood wait: {wait_time} seconds")
    print(f"⏳ الانتظار {wait_time} ثانية...")
    await asyncio.sleep(wait_time)
    return True

# ===== [17] التشغيل الرئيسي =====
def main():
    print("🚀 بدء تشغيل البوت الذكي...")
    print("✅ تهيئة قاعدة البيانات...")
    init_database()
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            session_file = "railway_final_pro.session"
            if os.path.exists(session_file):
                os.remove(session_file)
                print("✅ تم حذف ملف الجلسة القديم")
            
            print(f"📡 محاولة التشغيل {retry_count + 1}/{max_retries}")
            
            if not BOT_TOKEN:
                print("❌ خطأ: BOT_TOKEN غير موجود")
                return
            
            print("✅ تم التحقق من التوكن")
            print("🤖 تشغيل البوت الذكي...")
            
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
        print("✅ تم تشغيل البوت الذكي بنجاح!")

# ===== [18] نقطة الدخول =====
if __name__ == "__main__":
    main()
