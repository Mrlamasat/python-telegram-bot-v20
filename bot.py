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

# ===== [1.1] التحكم اليدوي في الأزرار (عدل هذه القيمة فقط) =====
SHOW_MORE_BUTTONS = True  # ✅ True = مفعلة, False = معطلة

# ===== [2] نظام قاعدة البيانات المحسن =====
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
                1, 10,
                dsn=DATABASE_URL,
                sslmode="require"
            )
            logging.info("✅ تم إنشاء Connection Pool")
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
    # جدول الفيديوهات
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            status TEXT DEFAULT 'posted',
            quality TEXT,
            duration TEXT,
            poster_id TEXT,
            views_today INTEGER DEFAULT 0,
            views_total INTEGER DEFAULT 0,
            last_viewed DATE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # جدول المستخدمين
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    # جدول المشاهدات التفصيلية
    db_query("""
        CREATE TABLE IF NOT EXISTS views_log (
            id SERIAL PRIMARY KEY,
            v_id TEXT,
            user_id BIGINT,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            view_date DATE DEFAULT CURRENT_DATE
        )
    """, fetch=False)
    
    print("✅ تم إنشاء الجداول")

# ===== [4] دوال إحصائيات المشاهدات =====
def increment_view(v_id, user_id):
    """تسجيل مشاهدة وتحديث الإحصائيات"""
    today = datetime.now().date()
    
    # تحديث مشاهدات اليوم
    db_query("""
        UPDATE videos SET 
        views_today = views_today + 1,
        views_total = views_total + 1,
        last_viewed = %s
        WHERE v_id = %s
    """, (today, v_id), fetch=False)
    
    # تسجيل في سجل المشاهدات
    db_query("""
        INSERT INTO views_log (v_id, user_id, view_date) 
        VALUES (%s, %s, %s)
    """, (v_id, user_id, today), fetch=False)
    
    # تحديث آخر ظهور للمستخدم
    db_query("""
        UPDATE users SET last_seen = CURRENT_TIMESTAMP 
        WHERE user_id = %s
    """, (user_id,), fetch=False)

def reset_daily_views():
    """تصفير مشاهدات اليوم (تعمل تلقائياً كل يوم)"""
    db_query("UPDATE videos SET views_today = 0", fetch=False)
    logging.info("✅ تم تصفير مشاهدات اليوم")

# ===== [5] دالة استخراج اسم المسلسل ورقم الحلقة =====
def extract_title_and_episode(text):
    """تستخرج اسم المسلسل ورقم الحلقة من نص مثل 'المداح 3'"""
    if not text:
        return None, 0
    
    first_line = text.strip().split('\n')[0]
    
    patterns = [
        r'^(.+?)\s+(\d+)$',
        r'^(.+?)\s*-\s*(\d+)$',
        r'^(.+?)\s*:\s*(\d+)$',
        r'^(.+?)\s*:\s*\[(\d+)\]$',
        r'^(.+?)\s+\[(\d+)\]$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, first_line, re.UNICODE)
        if match:
            title = match.group(1).strip()
            ep_num = int(match.group(2))
            return title, ep_num
    
    return first_line[:100], 0

# ===== [6] دالة حساب مدة الفيديو =====
def format_duration(seconds):
    minutes = seconds // 60
    return f"{minutes} دقيقة"

# ===== [7] دالة إنشاء أزرار الحلقات =====
def create_episode_buttons(title, current_v_id, me_username):
    """إنشاء أزرار الحلقات الأخرى"""
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

# ===== [8] مراقبة قناة المصدر (للتعديلات) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def monitor_source_channel(client, message):
    """تراقب التعديلات على الفيديوهات في قناة المصدر"""
    try:
        # التأكد أنها رسالة فيديو أو تعديل على فيديو
        if not message.video:
            return
        
        v_id = str(message.id)
        raw_text = message.caption or ""
        
        # استخراج العنوان ورقم الحلقة
        title, ep_num = extract_title_and_episode(raw_text)
        
        if ep_num > 0:
            # تحديث قاعدة البيانات
            db_query("""
                INSERT INTO videos (v_id, title, ep_num, duration, status) 
                VALUES (%s, %s, %s, %s, 'posted')
                ON CONFLICT (v_id) DO UPDATE SET 
                title = EXCLUDED.title,
                ep_num = EXCLUDED.ep_num,
                duration = EXCLUDED.duration,
                updated_at = CURRENT_TIMESTAMP
            """, (v_id, title, ep_num, format_duration(message.video.duration)), fetch=False)
            
            logging.info(f"✅ تم تحديث الحلقة {v_id}: {title} - حلقة {ep_num}")
        
    except Exception as e:
        logging.error(f"خطأ في مراقبة القناة: {e}")

# ===== [9] دالة عرض الحلقة الذكية =====
async def show_episode(client, message, v_id):
    try:
        # البحث في قاعدة البيانات
        db_data = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id = %s", (v_id,))
        
        # إذا لم توجد في قاعدة البيانات، نجلبها من المصدر ونتحديثها
        if not db_data:
            waiting_msg = await message.reply_text("🔄 جاري تحضير الحلقة لأول مرة...")
            
            try:
                source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source_msg and source_msg.video:
                    raw_text = source_msg.caption or ""
                    title, ep_num = extract_title_and_episode(raw_text)
                    
                    if ep_num == 0:
                        ep_num = 1  # قيمة افتراضية
                    
                    # حفظ في قاعدة البيانات
                    db_query("""
                        INSERT INTO videos (v_id, title, ep_num, duration, status) 
                        VALUES (%s, %s, %s, %s, 'posted')
                        ON CONFLICT (v_id) DO NOTHING
                    """, (v_id, title, ep_num, format_duration(source_msg.video.duration)), fetch=False)
                    
                    await waiting_msg.delete()
                    
                    # استخدم البيانات الجديدة
                    title = title
                    ep = ep_num
                    quality = None
                    duration = format_duration(source_msg.video.duration)
                else:
                    await waiting_msg.edit_text("❌ الحلقة غير موجودة في قناة المصدر")
                    return
            except Exception as e:
                await waiting_msg.edit_text(f"❌ خطأ: {e}")
                return
        else:
            title, ep, quality, duration = db_data[0]
        
        # بناء أزرار المزيد من الحلقات
        keyboard = []
        
        if SHOW_MORE_BUTTONS:
            me = await client.get_me()
            episode_buttons = create_episode_buttons(title, v_id, me.username)
            if episode_buttons:
                keyboard.extend(episode_buttons)
        
        # إضافة زر القناة الاحتياطية
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        # نص العرض
        caption = f"<b>🎬 الحلقة {ep}</b>\n"
        if quality:
            caption += f"📺 الجودة: {quality}\n"
        if duration:
            caption += f"⏱ المدة: {duration}"
        
        # إرسال الفيديو
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
        
        # تسجيل المشاهدة
        if message.from_user:
            increment_view(v_id, message.from_user.id)
        
    except Exception as e:
        logging.error(f"خطأ في show_episode: {e}")
        await message.reply_text("⚠️ حدث خطأ")

# ===== [10] أمر البدء الذكي =====
@app.on_message(filters.command("start") & filters.private)
async def smart_start(client, message):
    # تسجيل المستخدم
    username = message.from_user.username or ""
    db_query("""
        INSERT INTO users (user_id, username, last_seen) 
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET 
        username = EXCLUDED.username,
        last_seen = CURRENT_TIMESTAMP
    """, (message.from_user.id, username), fetch=False)
    
    if len(message.command) > 1:
        v_id = message.command[1]
        await show_episode(client, message, v_id)
    else:
        welcome_text = """👋 **بوت المشاهدة الذكي**

⚡ مشاهدة ذكية - أول ضغط يحمل الحلقة تلقائياً
📊 إحصائيات دقيقة للمشاهدات

🆘 @Mohsen_7e"""
        await message.reply_text(welcome_text)

# ===== [11] أمر الإحصائيات المتقدمة =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def advanced_stats(client, message):
    # إحصائيات عامة
    total_eps = db_query("SELECT COUNT(*) FROM videos")[0][0]
    total_users = db_query("SELECT COUNT(*) FROM users")[0][0]
    total_views = db_query("SELECT SUM(views_total) FROM videos")[0][0] or 0
    
    # أكثر 10 مسلسلات مشاهدة اليوم
    top_today = db_query("""
        SELECT title, views_today 
        FROM videos 
        WHERE views_today > 0
        ORDER BY views_today DESC 
        LIMIT 10
    """)
    
    # أكثر 10 مسلسلات مشاهدة كل الوقت
    top_all_time = db_query("""
        SELECT title, views_total 
        FROM videos 
        WHERE views_total > 0
        ORDER BY views_total DESC 
        LIMIT 10
    """)
    
    # أقل 10 مسلسلات مشاهدة (مقترحة للحذف)
    worst_series = db_query("""
        SELECT title, views_total 
        FROM videos 
        GROUP BY title 
        ORDER BY views_total ASC 
        LIMIT 10
    """)
    
    text = f"📊 **إحصائيات المشاهدات المتقدمة**\n\n"
    text += f"📁 إجمالي الحلقات: {total_eps}\n"
    text += f"👥 المستخدمين: {total_users}\n"
    text += f"👀 إجمالي المشاهدات: {total_views}\n"
    text += f"🔘 أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}\n\n"
    
    text += "🔥 **الأكثر مشاهدة اليوم:**\n"
    if top_today:
        for title, views in top_today:
            text += f"• {title}: {views} مشاهدة\n"
    else:
        text += "• لا توجد مشاهدات اليوم\n"
    
    text += "\n🏆 **الأكثر مشاهدة كل الوقت:**\n"
    if top_all_time:
        for title, views in top_all_time:
            text += f"• {title}: {views} مشاهدة\n"
    
    text += "\n⚠️ **الأقل مشاهدة (مقترحة للحذف):**\n"
    if worst_series:
        for title, views in worst_series:
            if views == 0:
                text += f"• {title}: لم يشاهدها أحد ❌\n"
            else:
                text += f"• {title}: {views} مشاهدة فقط\n"
    
    await message.reply_text(text)

# ===== [12] أمر تصفير الإحصائيات اليومية (يدوي) =====
@app.on_message(filters.command("reset_daily") & filters.user(ADMIN_ID))
async def reset_daily_command(client, message):
    reset_daily_views()
    await message.reply_text("✅ تم تصفير مشاهدات اليوم")

# ===== [13] أمر اختبار الاتصال =====
@app.on_message(filters.command("test") & filters.user(ADMIN_ID))
async def test_command(client, message):
    await message.reply_text("✅ البوت يعمل بشكل طبيعي")

# ===== [14] مهمة تصفير المشاهدات اليومية تلقائياً =====
async def daily_reset_task():
    """تعمل كل يوم في منتصف الليل"""
    while True:
        now = datetime.now()
        # احسب الوقت المتبقي حتى منتصف الليل
        next_reset = datetime(now.year, now.month, now.day) + timedelta(days=1)
        seconds_until_reset = (next_reset - now).total_seconds()
        
        await asyncio.sleep(seconds_until_reset)
        reset_daily_views()

# ===== [15] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل البوت الذكي...")
    
    # تهيئة قاعدة البيانات
    init_database()
    
    # بدء مهمة التصفير اليومية
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(daily_reset_task())
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"📡 محاولة التشغيل {retry_count + 1}/{max_retries}")
            
            if not BOT_TOKEN:
                print("❌ BOT_TOKEN غير موجود")
                return
            
            app.run()
            break
            
        except FloodWait as e:
            retry_count += 1
            wait_time = e.value
            print(f"⏳ Flood wait: {wait_time} ثانية")
            time.sleep(wait_time)
                
        except Exception as e:
            retry_count += 1
            print(f"❌ خطأ: {type(e).__name__}: {e}")
            if retry_count < max_retries:
                time.sleep(30 * retry_count)
    
    if retry_count >= max_retries:
        print("❌ فشل تشغيل البوت")
    else:
        print("✅ تم تشغيل البوت بنجاح!")

if __name__ == "__main__":
    main()
