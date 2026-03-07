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
    -1003790915936,
    -1003678294148,
    -1003690441303
]

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [1.1] متغيرات التحكم =====
SHOW_MORE_BUTTONS = False
AUTO_POST_ENABLED = True

# ===== [1.2] تخزين حالة النشر المؤقتة =====
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

# ===== [4] دالة استخراج اسم المسلسل ورقم الحلقة =====
def extract_title_and_episode(text):
    if not text:
        return None, 0
    
    first_line = text.strip().split('\n')[0]
    
    patterns = [
        r'^(.+?)\s+(\d+)$',
        r'^(.+?)\s*-\s*(\d+)$',
        r'^(.+?)\s*:\s*(\d+)$',
        r'^(.+?)\s*:\s*\[(\d+)\]$',
        r'^(.+?)\s+\[(\d+)\]$',
        r'^(.+?)\s*[#](\d+)$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, first_line, re.UNICODE)
        if match:
            title = match.group(1).strip()
            ep_num = int(match.group(2))
            return title, ep_num
    
    return first_line[:100], 0

# ===== [5] نظام النشر التلقائي =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def handle_new_video(client, message):
    """
    عند رفع فيديو جديد في قناة المصدر
    """
    try:
        # التأكد أنه فيديو
        if not message.video:
            return
        
        v_id = str(message.id)
        
        # تخزين معلومات الفيديو مؤقتاً
        pending_posts[v_id] = {
            'message_id': message.id,
            'caption': message.caption or "",
            'status': 'pending',
            'step': 'waiting_for_details'
        }
        
        # إرسال طلب للمشرف
        await client.send_message(
            ADMIN_ID,
            f"📹 **تم رفع فيديو جديد**\n\n"
            f"المعرف: `{v_id}`\n"
            f"الرجاء إرسال:\n"
            f"1️⃣ رقم الحلقة\n"
            f"2️⃣ جودة الفيديو (اختياري)\n"
            f"3️⃣ رابط البوستر (اختياري)\n\n"
            f"بالصيغة: `رقم_الحلقة الجودة رابط_البوستر`\n"
            f"مثال: `13 1080p https://t.me/...`"
        )
        
    except Exception as e:
        logging.error(f"خطأ في معالجة الفيديو الجديد: {e}")

# ===== [6] استقبال تفاصيل الحلقة من المشرف =====
@app.on_message(filters.command("post") & filters.user(ADMIN_ID))
async def receive_post_details(client, message):
    """
    استقبال تفاصيل الحلقة من المشرف
    """
    command = message.text.split()
    if len(command) < 5:
        return await message.reply_text(
            "❌ **صيغة غير صحيحة**\n\n"
            "استخدم: `/post v_id ep_num quality poster_url`\n"
            "مثال: `/post 3514 13 1080p https://t.me/poster/123`"
        )
    
    v_id = command[1]
    ep_num = int(command[2])
    quality = command[3]
    poster_url = command[4]
    
    try:
        # جلب الفيديو من قناة المصدر
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not source_msg or not source_msg.video:
            return await message.reply_text("❌ الفيديو غير موجود")
        
        # استخراج اسم المسلسل من الوصف
        raw_text = source_msg.caption or ""
        title, _ = extract_title_and_episode(raw_text)
        if not title:
            title = raw_text.split('\n')[0][:100]
        
        # حفظ في قاعدة البيانات
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, quality, poster_id, status) 
            VALUES (%s, %s, %s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num,
            quality = EXCLUDED.quality,
            poster_id = EXCLUDED.poster_id
        """, (v_id, title, ep_num, quality, poster_url), fetch=False)
        
        # إنشاء زر المشاهدة
        me = await client.get_me()
        watch_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
        ]])
        
        # النشر في جميع قنوات النشر
        for channel_id in PUBLIC_CHANNELS:
            try:
                # نشر البوستر أولاً (إذا وجد)
                if poster_url != "none" and poster_url.startswith("https://"):
                    await client.send_photo(
                        channel_id,
                        poster_url,
                        caption=f"🎬 {title}\nالحلقة {ep_num}\nجودة {quality}"
                    )
                
                # نشر الفيديو
                await client.copy_message(
                    channel_id,
                    SOURCE_CHANNEL,
                    int(v_id),
                    caption=f"🎬 {title} - الحلقة {ep_num}\nجودة: {quality}",
                    reply_markup=watch_button
                )
                
            except Exception as e:
                await message.reply_text(f"⚠️ خطأ في النشر للقناة {channel_id}: {e}")
        
        # إعلام المشرف بالنجاح
        await message.reply_text(
            f"✅ **تم النشر بنجاح**\n\n"
            f"المسلسل: {title}\n"
            f"رقم الحلقة: {ep_num}\n"
            f"الجودة: {quality}\n"
            f"تم النشر في {len(PUBLIC_CHANNELS)} قنوات"
        )
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [7] أمر النشر السريع =====
@app.on_message(filters.command("quick_post") & filters.user(ADMIN_ID))
async def quick_post(client, message):
    """
    نشر سريع للحلقة بدون تفاصيل إضافية
    """
    command = message.text.split()
    if len(command) < 3:
        return await message.reply_text("❌ استخدم: /quick_post v_id ep_num")
    
    v_id = command[1]
    ep_num = int(command[2])
    
    try:
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not source_msg or not source_msg.video:
            return await message.reply_text("❌ الفيديو غير موجود")
        
        raw_text = source_msg.caption or ""
        title, _ = extract_title_and_episode(raw_text)
        if not title:
            title = raw_text.split('\n')[0][:100]
        
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status) 
            VALUES (%s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num
        """, (v_id, title, ep_num), fetch=False)
        
        me = await client.get_me()
        watch_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")
        ]])
        
        for channel_id in PUBLIC_CHANNELS:
            await client.copy_message(
                channel_id,
                SOURCE_CHANNEL,
                int(v_id),
                caption=f"🎬 {title} - الحلقة {ep_num}",
                reply_markup=watch_button
            )
        
        await message.reply_text(f"✅ تم النشر السريع في {len(PUBLIC_CHANNELS)} قنوات")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [8] أمر عرض الحلقة =====
async def show_episode(client, message, v_id):
    try:
        db_data = db_query("SELECT title, ep_num, quality FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            return await message.reply_text("❌ الحلقة غير موجودة")
        
        title, ep, quality = db_data[0]
        
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
        
        caption = f"<b>{title} - الحلقة {ep}</b>"
        if quality:
            caption += f"\nجودة: {quality}"
        
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
        logging.error(f"خطأ: {e}")
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
        welcome_text = """👋 **بوت النشر التلقائي**

⚡ **مميزات البوت:**
• نشر تلقائي في 4 قنوات
• إضافة بوستر وجودة
• تحديث فوري لقاعدة البيانات

📝 **أوامر المشرف:**
/post - نشر مع تفاصيل
/quick_post - نشر سريع
/toggle_buttons - تشغيل/إيقاف الأزرار
/stats - عرض الإحصائيات

🆘 @Mohsen_7e"""
        await message.reply_text(welcome_text)

# ===== [10] أوامر التحكم =====
@app.on_message(filters.command("toggle_buttons") & filters.user(ADMIN_ID))
async def toggle_buttons(client, message):
    global SHOW_MORE_BUTTONS
    SHOW_MORE_BUTTONS = not SHOW_MORE_BUTTONS
    status = "✅ مفعلة" if SHOW_MORE_BUTTONS else "❌ معطلة"
    await message.reply_text(f"أزرار المزيد: {status}")

@app.on_message(filters.command("toggle_auto") & filters.user(ADMIN_ID))
async def toggle_auto(client, message):
    global AUTO_POST_ENABLED
    AUTO_POST_ENABLED = not AUTO_POST_ENABLED
    status = "✅ مفعل" if AUTO_POST_ENABLED else "❌ معطل"
    await message.reply_text(f"النشر التلقائي: {status}")

# ===== [11] أمر فحص القناة =====
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
                title, ep_num = extract_title_and_episode(raw_text)
                
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

# ===== [12] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def smart_stats(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    views = db_query("SELECT COUNT(*) FROM views_log")[0][0]
    
    text = f"🤖 **الإحصائيات**\n\n"
    text += f"📁 الحلقات: {total}\n"
    text += f"👥 المستخدمين: {users}\n"
    text += f"👀 المشاهدات: {views}\n"
    text += f"🔘 أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}\n"
    text += f"⚡ نشر تلقائي: {'مفعل' if AUTO_POST_ENABLED else 'معطل'}"
    
    await message.reply_text(text)

# ===== [13] التشغيل الرئيسي =====
def main():
    print("🚀 تشغيل بوت النشر التلقائي...")
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
