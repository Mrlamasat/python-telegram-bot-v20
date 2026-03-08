import os, psycopg2, logging, re, asyncio, time, json
from datetime import datetime, timedelta
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, ChannelInvalid, ChannelPrivate
from psycopg2 import pool

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
pending_posts = {}

# ===== [2] نظام قاعدة البيانات المحسن (مع Connection Pool) =====
class DatabasePool:
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance
    
    def _initialize_pool(self):
        try:
            self._pool = psycopg2.pool.SimpleConnectionPool(
                1, 20,  # min 1, max 20 connections
                dsn=DATABASE_URL,
                sslmode="require"
            )
            logging.info("✅ تم إنشاء Connection Pool بنجاح")
        except Exception as e:
            logging.error(f"❌ فشل إنشاء Connection Pool: {e}")
            self._pool = None
    
    def get_connection(self):
        if self._pool:
            return self._pool.getconn()
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    
    def return_connection(self, conn):
        if self._pool:
            self._pool.putconn(conn)
        else:
            conn.close()
    
    def close_all(self):
        if self._pool:
            self._pool.closeall()

db_pool = DatabasePool()

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = db_pool.get_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else None
        conn.commit()
        cur.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []
    finally:
        if conn:
            db_pool.return_connection(conn)

# ===== [3] إنشاء الجداول =====
def init_database():
    # إنشاء جدول الإعدادات (لتخزين حالة الأزرار)
    db_query("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # إدراج قيمة افتراضية لأزرار المزيد
    db_query("""
        INSERT INTO bot_settings (key, value) 
        VALUES ('show_more_buttons', 'false')
        ON CONFLICT (key) DO NOTHING
    """, fetch=False)
    
    # إنشاء جدول الطلبات المعلقة (بدلاً من الذاكرة)
    db_query("""
        CREATE TABLE IF NOT EXISTS pending_posts (
            v_id TEXT PRIMARY KEY,
            data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP + INTERVAL '1 day'
        )
    """, fetch=False)
    
    # إنشاء جدول الفيديوهات
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
    
    # إنشاء جدول المستخدمين
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
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
    
    print("✅ تم إنشاء الجداول بنجاح")

# ===== [4] دوال إدارة حالة الأزرار (مخزنة في قاعدة البيانات) =====
def get_show_more_buttons():
    result = db_query("SELECT value FROM bot_settings WHERE key = 'show_more_buttons'")
    if result and result[0][0] == 'true':
        return True
    return False

def set_show_more_buttons(value):
    str_value = 'true' if value else 'false'
    db_query("UPDATE bot_settings SET value = %s, updated_at = CURRENT_TIMESTAMP WHERE key = 'show_more_buttons'", (str_value,), fetch=False)

# ===== [5] دوال إدارة الطلبات المعلقة (بدلاً من الذاكرة) =====
def save_pending_post(v_id, data):
    db_query("""
        INSERT INTO pending_posts (v_id, data, expires_at) 
        VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '1 day')
        ON CONFLICT (v_id) DO UPDATE SET 
        data = EXCLUDED.data,
        expires_at = EXCLUDED.expires_at
    """, (v_id, json.dumps(data)), fetch=False)

def get_pending_post(v_id):
    result = db_query("SELECT data FROM pending_posts WHERE v_id = %s AND expires_at > CURRENT_TIMESTAMP", (v_id,))
    if result:
        return json.loads(result[0][0])
    return None

def delete_pending_post(v_id):
    db_query("DELETE FROM pending_posts WHERE v_id = %s", (v_id,), fetch=False)

def clean_expired_posts():
    db_query("DELETE FROM pending_posts WHERE expires_at <= CURRENT_TIMESTAMP", fetch=False)

# ===== [6] دالة استخراج اسم المسلسل =====
def extract_series_name(text):
    if not text:
        return "مسلسل"
    return text.strip().split('\n')[0][:100]

# ===== [7] دالة حساب مدة الفيديو =====
def format_duration(seconds):
    minutes = seconds // 60
    return f"{minutes} دقيقة"

# ===== [8] دالة إنشاء أزرار الحلقات (مع Pagination) =====
def create_episode_buttons(title, current_v_id, me_username):
    """إنشاء أزرار الحلقات مع Pagination (10 أزرار فقط)"""
    other_eps = db_query("""
        SELECT ep_num, v_id FROM videos 
        WHERE title = %s AND ep_num > 0 AND v_id != %s
        ORDER BY ep_num ASC
        LIMIT 30
    """, (title, current_v_id))
    
    if not other_eps:
        return []
    
    keyboard = []
    row = []
    
    for i, (o_ep, o_vid) in enumerate(other_eps, 1):
        row.append(InlineKeyboardButton(
            str(o_ep), 
            url=f"https://t.me/{me_username}?start={o_vid}"
        ))
        if i % 5 == 0:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    return keyboard

# ===== [9] مراقبة قناة المصدر (معدلة لاستخدام قاعدة البيانات) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def monitor_source_channel(client, message):
    try:
        if message.video:
            v_id = str(message.id)
            series_name = extract_series_name(message.caption or "")
            duration = format_duration(message.video.duration) if message.video.duration else "45 دقيقة"
            
            data = {
                'video_id': v_id,
                'series_name': series_name,
                'duration': duration,
                'status': 'waiting_for_poster',
                'video_message_id': message.id
            }
            
            save_pending_post(v_id, data)
            
            await client.send_message(
                SOURCE_CHANNEL,
                f"🖼 **الخطوة التالية:**\nالرجاء رفع **البوستر** الخاص بالحلقة"
            )
            return

        if message.photo:
            # تنظيف الطلبات المنتهية
            clean_expired_posts()
            
            # البحث عن طلب معلق
            all_pending = db_query("SELECT v_id, data FROM pending_posts WHERE expires_at > CURRENT_TIMESTAMP")
            
            for v_id, data_json in all_pending:
                data = json.loads(data_json)
                if data.get('status') == 'waiting_for_poster':
                    data['poster_id'] = message.id
                    data['poster_message_id'] = message.id
                    data['status'] = 'waiting_for_details'
                    save_pending_post(v_id, data)
                    
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
            text = message.text.strip()
            match = re.search(r'(\d+)(?:\s+)?(.+)?', text)
            
            if match:
                ep_num = int(match.group(1))
                quality = match.group(2) if match.group(2) else "HD"
                
                # البحث عن طلب معلق في انتظار التفاصيل
                all_pending = db_query("SELECT v_id, data FROM pending_posts WHERE expires_at > CURRENT_TIMESTAMP")
                
                for v_id, data_json in all_pending:
                    data = json.loads(data_json)
                    if data.get('status') == 'waiting_for_details':
                        data['ep_num'] = ep_num
                        data['quality'] = quality
                        await publish_to_channel(client, v_id, data)
                        return
                
                await client.send_message(
                    SOURCE_CHANNEL,
                    "📝 تم استلام النص ولكن لا توجد حلقة في انتظار التفاصيل."
                )
            else:
                await client.send_message(
                    SOURCE_CHANNEL,
                    "❌ صيغة غير صحيحة. مثال: `18 1080p`"
                )
            
    except Exception as e:
        logging.error(f"خطأ في مراقبة القناة: {e}")

# ===== [10] دالة النشر في القناة =====
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
        
        # حذف الطلب المعلق
        delete_pending_post(v_id)
        
        logging.info(f"✅ تم نشر البوستر للحلقة {v_id}: {series_name} - حلقة {ep_num}")
        
    except Exception as e:
        logging.error(f"خطأ في النشر: {e}")
        await client.send_message(
            SOURCE_CHANNEL,
            f"❌ حدث خطأ أثناء النشر: {e}"
        )

# ===== [11] دالة عرض الحلقة في البوت =====
async def show_episode(client, message, v_id):
    try:
        db_data = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            return await message.reply_text("❌ الحلقة غير متوفرة")
        
        title, ep, quality, duration = db_data[0]
        
        # بناء أزرار المزيد من الحلقات
        keyboard = []
        
        if get_show_more_buttons():
            me = await client.get_me()
            episode_buttons = create_episode_buttons(title, v_id, me.username)
            if episode_buttons:
                keyboard.extend(episode_buttons)
        
        # إضافة زر القناة الاحتياطية
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

# ===== [12] أمر البدء =====
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

# ===== [13] أمر التحكم في أزرار المزيد =====
@app.on_message(filters.command("toggle_buttons") & filters.user(ADMIN_ID))
async def toggle_buttons(client, message):
    current = get_show_more_buttons()
    new_value = not current
    set_show_more_buttons(new_value)
    status = "✅ مفعلة" if new_value else "❌ معطلة"
    await message.reply_text(f"أزرار المزيد من الحلقات: {status}")

# ===== [14] أمر فحص القناة (معدل) =====
@app.on_message(filters.command("scan_source") & filters.user(ADMIN_ID))
async def scan_source_command(client, message):
    msg = await message.reply_text("🔄 جاري فحص قناة المصدر...")
    
    stats = {'scanned': 0, 'updated': 0, 'errors': 0}
    
    try:
        # التأكد من أن البوت عضو في القناة
        try:
            chat = await client.get_chat(SOURCE_CHANNEL)
            await msg.edit_text(f"✅ تم الاتصال بقناة المصدر: {chat.title}\n🔄 جاري جلب الرسائل...")
        except Exception as e:
            await msg.edit_text(f"❌ البوت ليس عضواً في قناة المصدر")
            return
        
        # جلب آخر 200 رسالة من القناة (مع معالجة الأخطاء)
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
        await msg.edit_text(f"❌ خطأ: {e}")
        return
    
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    buttons_status = "مفعلة" if get_show_more_buttons() else "معطلة"
    result = f"""✅ **تم الفحص**

📊 الإحصائيات:
• رسائل ممسوحة: {stats['scanned']}
• حلقات محدثة: {stats['updated']}
• أخطاء: {stats['errors']}

📁 إجمالي الحلقات: {total}
🔘 حالة أزرار المزيد: {buttons_status}"""
    await msg.edit_text(result)

# ===== [15] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def smart_stats(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    views = db_query("SELECT COUNT(*) FROM views_log")[0][0]
    
    # جلب آخر 5 حلقات مضافة
    recent = db_query("""
        SELECT title, ep_num FROM videos 
        ORDER BY created_at DESC LIMIT 5
    """)
    
    buttons_status = "مفعلة" if get_show_more_buttons() else "معطلة"
    
    text = f"🤖 **إحصائيات البوت**\n\n"
    text += f"📁 إجمالي الحلقات: {total}\n"
    text += f"👥 عدد المستخدمين: {users}\n"
    text += f"👀 عدد المشاهدات: {views}\n"
    text += f"🔘 أزرار المزيد: {buttons_status}\n\n"
    text += "🆕 **آخر 5 حلقات مضافة:**\n"
    
    for title, ep in recent:
        text += f"• {title} - حلقة {ep}\n"
    
    await message.reply_text(text)

# ===== [16] أمر اختبار الاتصال بالقنوات =====
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
    
    await msg.edit_text(result)

# ===== [17] أمر تنظيف الطلبات المنتهية =====
@app.on_message(filters.command("clean_pending") & filters.user(ADMIN_ID))
async def clean_pending(client, message):
    clean_expired_posts()
    await message.reply_text("✅ تم تنظيف الطلبات المنتهية")

# ===== [18] التشغيل الرئيسي (بدون حذف ملف الجلسة) =====
def main():
    print("🚀 تشغيل البوت...")
    
    # تهيئة قاعدة البيانات
    init_database()
    
    # تنظيف الطلبات المنتهية
    clean_expired_posts()
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # لا تحذف ملف الجلسة! هذا مهم جداً
            print(f"📡 محاولة التشغيل {retry_count + 1}/{max_retries}")
            
            if not BOT_TOKEN:
                print("❌ BOT_TOKEN غير موجود")
                return
            
            print("✅ تم التحقق من التوكن")
            app.run()
            break
            
        except FloodWait as e:
            retry_count += 1
            wait_time = e.value
            print(f"⏳ Flood wait: {wait_time} ثانية")
            
            # تخزين الوقت المتبقي في قاعدة البيانات
            if wait_time > 300:  # أكثر من 5 دقائق
                print("⚠️ وقت انتظار طويل، سيتم إعادة المحاولة لاحقاً")
                time.sleep(60)  # انتظر دقيقة وحاول مجدداً
            else:
                time.sleep(wait_time)
                
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

# ===== [19] معالجة إيقاف التشغيل =====
import atexit

@atexit.register
def cleanup():
    """تنظيف عند إيقاف البوت"""
    print("🔄 جاري تنظيف الاتصالات...")
    db_pool.close_all()
    print("✅ تم تنظيف الاتصالات")

if __name__ == "__main__":
    main()
