import os, psycopg2, logging, re, asyncio, time, random
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

# قناة النشر الوحيدة
PUBLISH_CHANNEL = -1003554018307

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [1.1] متغيرات التحكم =====
SHOW_MORE_BUTTONS = False  # يبدأ معطلاً، يشغل بـ /toggle_buttons
pending_posts = {}

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
    try:
        db_query("ALTER TABLE videos ADD COLUMN IF NOT EXISTS quality TEXT", fetch=False)
        db_query("ALTER TABLE videos ADD COLUMN IF NOT EXISTS duration TEXT", fetch=False)
    except:
        pass
    
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            status TEXT DEFAULT 'posted',
            quality TEXT,
            duration TEXT,
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

# ===== [4] دالة استخراج اسم المسلسل الطبيعي =====
def extract_series_name(text):
    if not text:
        return "مسلسل"
    return text.strip().split('\n')[0][:100]

# ===== [5] دالة حساب مدة الفيديو =====
def format_duration(seconds):
    minutes = seconds // 60
    return f"{minutes} دقيقة"

# ===== [6] مراقبة قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def monitor_source_channel(client, message):
    try:
        if message.video:
            v_id = str(message.id)
            series_name = extract_series_name(message.caption or "")
            duration = format_duration(message.video.duration) if message.video.duration else "45 دقيقة"
            
            pending_posts[v_id] = {
                'video_id': v_id,
                'series_name': series_name,
                'duration': duration,
                'status': 'waiting_for_poster',
                'video_message_id': message.id
            }
            
            await client.send_message(
                SOURCE_CHANNEL,
                f"🖼 **الخطوة التالية:**\nالرجاء رفع **البوستر** الخاص بالحلقة"
            )
            return

        if message.photo:
            for v_id, data in list(pending_posts.items()):
                if data['status'] == 'waiting_for_poster':
                    data['poster_id'] = message.id
                    data['poster_message_id'] = message.id
                    data['status'] = 'waiting_for_details'
                    
                    await client.send_message(
                        SOURCE_CHANNEL,
                        f"🔢 **الخطوة التالية:**\nالرجاء إرسال **رقم الحلقة والجودة**\nمثال: `18 1080p`"
                    )
                    return
            
            await client.send_message(
                SOURCE_CHANNEL,
                "⚠️ تم رفع صورة ولكن لا يوجد فيديو في انتظار البوستر."
            )
            return

        if message.text and not message.text.startswith('/'):
            for v_id, data in list(pending_posts.items()):
                if data['status'] == 'waiting_for_details':
                    text = message.text.strip()
                    match = re.search(r'(\d+)(?:\s+)?(.+)?', text)
                    
                    if match:
                        ep_num = int(match.group(1))
                        quality = match.group(2) if match.group(2) else "HD"
                        
                        data['ep_num'] = ep_num
                        data['quality'] = quality
                        
                        await publish_to_channel(client, v_id, data)
                        return
                    else:
                        await client.send_message(
                            SOURCE_CHANNEL,
                            "❌ صيغة غير صحيحة. مثال: `18 1080p`"
                        )
                        return
            
            await client.send_message(
                SOURCE_CHANNEL,
                "📝 تم استلام النص ولكن لا توجد حلقة في انتظار التفاصيل."
            )
            
    except Exception as e:
        logging.error(f"خطأ في مراقبة القناة: {e}")

# ===== [7] دالة النشر في القناة =====
async def publish_to_channel(client, v_id, data):
    try:
        series_name = data['series_name']
        ep_num = data['ep_num']
        quality = data['quality']
        duration = data['duration']
        
        # حفظ في قاعدة البيانات
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, quality, duration, status, poster_id) 
            VALUES (%s, %s, %s, %s, %s, 'posted', %s)
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num,
            quality = EXCLUDED.quality,
            duration = EXCLUDED.duration,
            poster_id = EXCLUDED.poster_id
        """, (v_id, series_name, ep_num, quality, duration, str(data['poster_message_id'])), fetch=False)
        
        # إنشاء رابط البوت
        me = await client.get_me()
        bot_link = f"https://t.me/{me.username}?start={v_id}"
        
        watch_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 مشاهدة الحلقة", url=bot_link)
        ]])
        
        # نشر البوستر في القناة
        sent_message = await client.copy_message(
            PUBLISH_CHANNEL,
            SOURCE_CHANNEL,
            data['poster_message_id'],
            caption=f"الحلقة {ep_num}\n{quality} | {duration}",
            reply_markup=watch_button
        )
        
        # الحصول على رابط المنشور
        channel_username = None
        try:
            chat = await client.get_chat(PUBLISH_CHANNEL)
            if chat.username:
                channel_username = chat.username
        except:
            pass
        
        if channel_username:
            post_link = f"https://t.me/{channel_username}/{sent_message.id}"
        else:
            post_link = f"https://t.me/c/{str(PUBLISH_CHANNEL).replace('-100', '')}/{sent_message.id}"
        
        # إرسال تأكيد للمشرف مع رابط النشر
        await client.send_message(
            SOURCE_CHANNEL,
            f"✅ **تم النشر بنجاح!**\n"
            f"رقم الحلقة: {ep_num}\n"
            f"🔗 رابط المنشور: {post_link}"
        )
        
        logging.info(f"✅ تم نشر البوستر للحلقة {v_id}: {series_name} - حلقة {ep_num}")
        
        del pending_posts[v_id]
        
    except Exception as e:
        logging.error(f"خطأ في النشر: {e}")
        await client.send_message(
            SOURCE_CHANNEL,
            f"❌ حدث خطأ أثناء النشر: {e}\nتأكد من أن البوت مشرف في قناة النشر"
        )

# ===== [8] دالة عرض الحلقة في البوت =====
async def show_episode(client, message, v_id):
    try:
        db_data = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            return await message.reply_text("❌ الحلقة غير متوفرة")
        
        title, ep, quality, duration = db_data[0]
        
        keyboard = []
        
        # ✅ التحقق من SHOW_MORE_BUTTONS وتشغيل الأزرار إذا كان مفعلاً
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
        
        # في البوت - يظهر رقم الحلقة
        caption = f"<b>🎬 الحلقة {ep}</b>\n"
        if quality:
            caption += f"📺 الجودة: {quality}\n"
        if duration:
            caption += f"⏱ المدة: {duration}"
        
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=caption,
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
        logging.error(f"خطأ في show_episode: {e}")
        await message.reply_text("⚠️ حدث خطأ")

# ===== [9] أمر البدء =====
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
        welcome_text = """👋 **بوت المشاهدة**

⚡ مشاهدة آمنة وخاصة

🆘 @Mohsen_7e"""
        await message.reply_text(welcome_text)

# ===== [10] أمر التحكم في أزرار المزيد =====
@app.on_message(filters.command("toggle_buttons") & filters.user(ADMIN_ID))
async def toggle_buttons(client, message):
    global SHOW_MORE_BUTTONS
    SHOW_MORE_BUTTONS = not SHOW_MORE_BUTTONS
    status = "✅ مفعلة" if SHOW_MORE_BUTTONS else "❌ معطلة"
    await message.reply_text(f"أزرار المزيد من الحلقات: {status}")

# ===== [11] أمر فحص القناة (معدل ليعمل مع القنوات الخاصة) =====
@app.on_message(filters.command("scan_source") & filters.user(ADMIN_ID))
async def scan_source_command(client, message):
    msg = await message.reply_text("🔄 جاري فحص قناة المصدر...")
    
    stats = {'scanned': 0, 'updated': 0, 'errors': 0}
    
    try:
        # التأكد من أن البوت عضو في القناة
        try:
            chat = await client.get_chat(SOURCE_CHANNEL)
            await msg.edit_text(f"✅ تم الاتصال بقناة المصدر: {chat.title}")
        except Exception as e:
            await msg.edit_text(f"❌ البوت ليس عضواً في قناة المصدر\nالرجاء إضافة البوت كمشرف في القناة أولاً")
            return
        
        # جلب آخر 200 رسالة من القناة
        async for post in client.get_chat_history(SOURCE_CHANNEL, limit=200):
            stats['scanned'] += 1
            
            try:
                if not (post.caption or post.text) or not post.video:
                    continue
                    
                raw_text = post.caption or post.text
                v_id = str(post.id)
                title = extract_series_name(raw_text)
                
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
                logging.error(f"خطأ في فحص الرسالة: {e}")
            
            if stats['updated'] % 20 == 0 and stats['updated'] > 0:
                await msg.edit_text(f"🔄 تم تحديث {stats['updated']} حلقة...")
    
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}\nتأكد من أن البوت مشرف في القناة")
        return
    
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    result = f"""✅ **تم الفحص**

📊 الإحصائيات:
• رسائل ممسوحة: {stats['scanned']}
• حلقات محدثة: {stats['updated']}
• أخطاء: {stats['errors']}

📁 إجمالي الحلقات في قاعدة البيانات: {total}
🔘 حالة أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}"""
    await msg.edit_text(result)

# ===== [12] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def smart_stats(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    views = db_query("SELECT COUNT(*) FROM views_log")[0][0]
    
    # جلب آخر 5 حلقات مضافة
    recent = db_query("""
        SELECT title, ep_num, created_at FROM videos 
        ORDER BY created_at DESC LIMIT 5
    """)
    
    text = f"🤖 **إحصائيات البوت**\n\n"
    text += f"📁 إجمالي الحلقات: {total}\n"
    text += f"👥 عدد المستخدمين: {users}\n"
    text += f"👀 عدد المشاهدات: {views}\n"
    text += f"🔘 أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}\n\n"
    text += "🆕 **آخر 5 حلقات مضافة:**\n"
    
    for title, ep, date in recent:
        text += f"• {title} - حلقة {ep}\n"
    
    await message.reply_text(text)

# ===== [13] أمر اختبار الاتصال بالقنوات =====
@app.on_message(filters.command("test_channels") & filters.user(ADMIN_ID))
async def test_channels(client, message):
    msg = await message.reply_text("🔄 جاري اختبار الاتصال بالقنوات...")
    
    result = "📊 **نتائج اختبار القنوات:**\n\n"
    
    # اختبار قناة المصدر
    try:
        chat = await client.get_chat(SOURCE_CHANNEL)
        result += f"✅ قناة المصدر: {chat.title}\n"
    except Exception as e:
        result += f"❌ قناة المصدر: غير متصل - {e}\n"
    
    # اختبار قناة النشر
    try:
        chat = await client.get_chat(PUBLISH_CHANNEL)
        result += f"✅ قناة النشر: {chat.title}\n"
    except Exception as e:
        result += f"❌ قناة النشر: غير متصل - {e}\n"
    
    # إرشادات
    result += "\n📝 **للإصلاح:**\n"
    result += "1. أضف البوت كمشرف في قناة المصدر\n"
    result += "2. أضف البوت كمشرف في قناة النشر\n"
    result += "3. تأكد من صلاحيات إرسال الرسائل"
    
    await msg.edit_text(result)

# ===== [14] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل البوت...")
    init_database()
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            session_file = "railway_final_pro.session"
            if os.path.exists(session_file):
                os.remove(session_file)
            
            print(f"📡 محاولة التشغيل {retry_count + 1}/{max_retries}")
            
            if not BOT_TOKEN:
                print("❌ BOT_TOKEN غير موجود")
                return
            
            app.run()
            break
            
        except FloodWait as e:
            retry_count += 1
            print(f"⏳ Flood wait: {e.value} ثانية")
            time.sleep(e.value)
                
        except Exception as e:
            retry_count += 1
            print(f"❌ خطأ: {e}")
            if retry_count < max_retries:
                time.sleep(30 * retry_count)
    
    if retry_count >= max_retries:
        print("❌ فشل تشغيل البوت بعد 5 محاولات")
    else:
        print("✅ تم تشغيل البوت بنجاح!")

if __name__ == "__main__":
    main()
