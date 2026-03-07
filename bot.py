import os, psycopg2, logging, re, asyncio, time
from datetime import datetime
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, ChannelInvalid, ChannelPrivate

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
]

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [1.1] متغيرات التحكم =====
SHOW_MORE_BUTTONS = False
pending_posts = {}  # لتخزين الحلقات قيد الانتظار

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

# ===== [3] إنشاء الجداول =====
def init_database():
    db_query("DROP TABLE IF EXISTS views_log", fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            status TEXT DEFAULT 'posted',
            quality TEXT,
            poster_id TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
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
    
    print("✅ تم إنشاء الجداول بنجاح")

# ===== [4] دالة استخراج اسم المسلسل =====
def extract_series_name(text):
    """تستخرج اسم المسلسل من أول سطر"""
    if not text:
        return "مسلسل"
    return text.strip().split('\n')[0][:100]

# ===== [5] مراقبة قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def monitor_source_channel(client, message):
    """
    تراقب قناة المصدر وتتفاعل مع:
    1. الفيديو الجديد
    2. البوستر الجديد
    3. رسالة رقم الحلقة
    """
    try:
        # الحالة 1: تم رفع فيديو جديد
        if message.video:
            v_id = str(message.id)
            
            # استخراج اسم المسلسل من الوصف (إذا كان موجوداً)
            series_name = extract_series_name(message.caption or "")
            
            # تخزين معلومات الفيديو مؤقتاً
            pending_posts[v_id] = {
                'video_id': v_id,
                'series_name': series_name,
                'status': 'waiting_for_poster',
                'video_message_id': message.id
            }
            
            # تفاعل: نطلب رفع البوستر
            await client.send_message(
                SOURCE_CHANNEL,
                f"🖼 **الخطوة التالية:**\nالرجاء رفع **البوستر** الخاص بـ {series_name}\n(سيتم النشر تلقائياً بعد اكتمال البيانات)"
            )
            
            logging.info(f"📹 تم رفع فيديو جديد {v_id} - ننتظر البوستر")
            return

        # الحالة 2: تم رفع بوستر (صورة)
        if message.photo:
            # نبحث عن آخر فيديو في انتظار البوستر
            for v_id, data in list(pending_posts.items()):
                if data['status'] == 'waiting_for_poster':
                    # تخزين البوستر
                    data['poster_id'] = message.id
                    data['poster_message_id'] = message.id
                    data['status'] = 'waiting_for_episode'
                    
                    # تفاعل: نطلب رقم الحلقة
                    await client.send_message(
                        SOURCE_CHANNEL,
                        f"🔢 **الخطوة التالية:**\nالرجاء إرسال **رقم الحلقة** لـ {data['series_name']}\nمثال: `13`"
                    )
                    
                    logging.info(f"🖼 تم رفع بوستر للفيديو {v_id} - ننتظر رقم الحلقة")
                    return
            
            # إذا لم نجد فيديو في الانتظار
            await client.send_message(
                SOURCE_CHANNEL,
                "⚠️ تم رفع صورة ولكن لا يوجد فيديو في انتظار البوستر.\nالرجاء رفع الفيديو أولاً."
            )
            return

        # الحالة 3: تم إرسال رسالة نصية (رقم الحلقة)
        if message.text and not message.text.startswith('/'):
            # نبحث عن فيديو في انتظار رقم الحلقة
            for v_id, data in list(pending_posts.items()):
                if data['status'] == 'waiting_for_episode':
                    # استخراج رقم الحلقة من النص
                    text = message.text.strip()
                    numbers = re.findall(r'\d+', text)
                    
                    if numbers:
                        ep_num = int(numbers[0])
                        data['ep_num'] = ep_num
                        
                        # ✅ اكتملت البيانات - نبدأ النشر
                        await complete_and_publish(client, v_id, data)
                        return
                    else:
                        await client.send_message(
                            SOURCE_CHANNEL,
                            "❌ لم أجد رقم صحيح. الرجاء إرسال رقم الحلقة فقط (مثال: 13)"
                        )
                        return
            
            # إذا لم نجد فيديو في الانتظار
            await client.send_message(
                SOURCE_CHANNEL,
                "📝 تم استلام النص ولكن لا توجد حلقة في انتظار الرقم."
            )
            
    except Exception as e:
        logging.error(f"خطأ في مراقبة القناة: {e}")

# ===== [6] دالة النشر بعد اكتمال البيانات =====
async def complete_and_publish(client, v_id, data):
    """تنشر الحلقة بعد اكتمال جميع البيانات"""
    try:
        # جلب الفيديو من قناة المصدر
        video_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        
        # جلب البوستر من قناة المصدر
        poster_msg = await client.get_messages(SOURCE_CHANNEL, data['poster_message_id'])
        
        series_name = data['series_name']
        ep_num = data['ep_num']
        
        # حفظ في قاعدة البيانات
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status, poster_id) 
            VALUES (%s, %s, %s, 'posted', %s)
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num,
            poster_id = EXCLUDED.poster_id
        """, (v_id, series_name, ep_num, str(data['poster_message_id'])), fetch=False)
        
        # إنشاء زر المشاهدة
        me = await client.get_me()
        watch_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
        ]])
        
        # النشر في جميع قنوات النشر
        for channel_id in PUBLIC_CHANNELS:
            try:
                # نشر البوستر أولاً
                await client.copy_message(
                    channel_id,
                    SOURCE_CHANNEL,
                    data['poster_message_id'],
                    caption=f"🎬 {series_name}\nالحلقة {ep_num}"
                )
                
                # نشر الفيديو
                await client.copy_message(
                    channel_id,
                    SOURCE_CHANNEL,
                    int(v_id),
                    caption=f"🎬 {series_name} - الحلقة {ep_num}",
                    reply_markup=watch_button
                )
                
            except Exception as e:
                logging.error(f"خطأ في النشر للقناة {channel_id}: {e}")
        
        # إرسال تأكيد في قناة المصدر
        await client.send_message(
            SOURCE_CHANNEL,
            f"✅ **تم النشر بنجاح!**\n"
            f"المسلسل: {series_name}\n"
            f"رقم الحلقة: {ep_num}\n"
            f"تم النشر في {len(PUBLIC_CHANNELS)} قنوات"
        )
        
        # حذف البيانات المؤقتة
        del pending_posts[v_id]
        
        logging.info(f"✅ تم نشر الحلقة {v_id}: {series_name} - حلقة {ep_num}")
        
    except Exception as e:
        logging.error(f"خطأ في النشر: {e}")
        await client.send_message(
            SOURCE_CHANNEL,
            f"❌ حدث خطأ أثناء النشر: {e}"
        )

# ===== [7] دالة عرض الحلقة =====
async def show_episode(client, message, v_id):
    try:
        db_data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            return await message.reply_text("❌ الحلقة غير موجودة")
        
        title, ep = db_data[0]
        
        keyboard = []
        
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
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=f"<b>{title} - الحلقة {ep}</b>",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
        
        try:
            if message.from_user:
                db_query(
                    "INSERT INTO views_log (v_id, user_id) VALUES (%s, %s)",
                    (v_id, message.from_user.id),
                    fetch=False
                )
        except:
            pass
        
    except Exception as e:
        logging.error(f"خطأ: {e}")
        await message.reply_text("⚠️ حدث خطأ")

# ===== [8] أمر البدء =====
@app.on_message(filters.command("start") & filters.private)
async def smart_start(client, message):
    username = message.from_user.username or ""
    db_query(
        "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username",
        (message.from_user.id, username),
        fetch=False
    )
    
    if len(message.command) > 1:
        v_id = message.command[1]
        await show_episode(client, message, v_id)
    else:
        welcome_text = """👋 **بوت النشر التلقائي**

⚡ **طريقة العمل في قناة المصدر:**
1️⃣ ارفع الفيديو
2️⃣ ارفع البوستر
3️⃣ اكتب رقم الحلقة
🤖 البوت ينشر تلقائياً في 4 قنوات!

🆘 @Mohsen_7e"""
        await message.reply_text(welcome_text)

# ===== [9] أمر التحكم في الأزرار =====
@app.on_message(filters.command("toggle_buttons") & filters.user(ADMIN_ID))
async def toggle_buttons(client, message):
    global SHOW_MORE_BUTTONS
    SHOW_MORE_BUTTONS = not SHOW_MORE_BUTTONS
    status = "✅ مفعلة" if SHOW_MORE_BUTTONS else "❌ معطلة"
    await message.reply_text(f"أزرار المزيد: {status}")

# ===== [10] أمر فحص القناة =====
@app.on_message(filters.command("scan_source") & filters.user(ADMIN_ID))
async def scan_source_command(client, message):
    msg = await message.reply_text("🔄 جاري فحص قناة المصدر...")
    
    stats = {'scanned': 0, 'updated': 0, 'errors': 0}
    
    try:
        async for post in client.get_chat_history(SOURCE_CHANNEL, limit=500):
            stats['scanned'] += 1
            
            try:
                if not (post.caption or post.text) or not post.video:
                    continue
                    
                raw_text = post.caption or post.text
                v_id = str(post.id)
                title = extract_series_name(raw_text)
                
                # محاولة استخراج رقم الحلقة من النص
                numbers = re.findall(r'\d+', raw_text)
                ep_num = int(numbers[0]) if numbers else 0
                
                if ep_num > 0:
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
            
            if stats['updated'] % 50 == 0:
                await msg.edit_text(f"🔄 تم تحديث {stats['updated']} حلقة...")
    
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")
        return
    
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    result = f"""✅ **تم الفحص**

📊 الإحصائيات:
• رسائل ممسوحة: {stats['scanned']}
• حلقات محدثة: {stats['updated']}
• أخطاء: {stats['errors']}

📁 إجمالي الحلقات: {total}"""
    await msg.edit_text(result)

# ===== [11] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def smart_stats(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    views = db_query("SELECT COUNT(*) FROM views_log")[0][0]
    
    text = f"🤖 **الإحصائيات**\n\n"
    text += f"📁 الحلقات: {total}\n"
    text += f"👥 المستخدمين: {users}\n"
    text += f"👀 المشاهدات: {views}\n"
    text += f"🔘 أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}"
    
    await message.reply_text(text)

# ===== [12] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل بوت التفاعل مع قناة المصدر...")
    init_database()
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            session_file = "railway_final_pro.session"
            if os.path.exists(session_file):
                os.remove(session_file)
            
            print(f"📡 محاولة {retry_count + 1}/{max_retries}")
            
            if not BOT_TOKEN:
                print("❌ BOT_TOKEN غير موجود")
                return
            
            app.run()
            break
            
        except FloodWait as e:
            retry_count += 1
            print(f"⏳ الانتظار {e.value} ثانية")
            time.sleep(e.value)
                
        except Exception as e:
            retry_count += 1
            print(f"❌ خطأ: {e}")
            if retry_count < max_retries:
                time.sleep(30 * retry_count)
    
    if retry_count >= max_retries:
        print("❌ فشل التشغيل")
    else:
        print("✅ تم التشغيل بنجاح!")

if __name__ == "__main__":
    main()
