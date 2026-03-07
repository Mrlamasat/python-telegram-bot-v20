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

# ===== [3] دالة استخراج رقم الحلقة من النص =====
def extract_ep_num_simple(text):
    """دالة لاستخراج رقم الحلقة من أي نص"""
    if not text:
        return 0
    
    text = str(text).strip()
    
    # أنماط البحث عن الأرقام
    patterns = [
        r'\[(\d+)\]',
        r'\((\d+)\)',
        r'الحلقة\s+(\d+)',
        r'الحلقه\s+(\d+)',
        r'(\d+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
        if match:
            return int(match.group(1))
    
    return 0

# ===== [4] دالة استخراج اسم المسلسل ورقم الحلقة من التنسيق الجديد =====
def extract_title_and_episode(text):
    """
    تستخرج اسم المسلسل ورقم الحلقة من نص مثل "المداح 13"
    أو "المداح - 13" أو "المداح: 13"
    """
    if not text:
        return None, 0
    
    # أخذ السطر الأول فقط
    first_line = text.strip().split('\n')[0]
    
    # أنماط التنسيق الجديد (كلمات ثم رقم)
    patterns = [
        r'^(.+?)\s+(\d+)$',           # "المداح 13"
        r'^(.+?)\s*-\s*(\d+)$',        # "المداح - 13"
        r'^(.+?)\s*:\s*(\d+)$',        # "المداح: 13"
        r'^(.+?)\s*:\s*\[(\d+)\]$',    # "المداح: [13]"
        r'^(.+?)\s+\[(\d+)\]$',        # "المداح [13]"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, first_line, re.UNICODE)
        if match:
            title = match.group(1).strip()
            ep_num = int(match.group(2))
            return title, ep_num
    
    # إذا لم يطابق النمط، نستخدم الطريقة القديمة
    return None, 0

# ===== [5] دالة البحث عن رقم الحلقة من قنوات النشر =====
async def get_episode_from_channels(client, v_id):
    """
    تبحث عن رقم الحلقة في قنوات النشر
    حيث يكون مكتوباً بجانب زر المشاهدة
    """
    try:
        for channel_id in PUBLIC_CHANNELS:
            try:
                async for post in client.get_chat_history(channel_id, limit=200):
                    if not post.reply_markup:
                        continue
                    
                    for row in post.reply_markup.inline_keyboard:
                        for btn in row:
                            if btn.url and f"start={v_id}" in btn.url:
                                # جمع كل النصوص المتاحة
                                full_text = ""
                                if post.caption:
                                    full_text += post.caption + " "
                                if post.text:
                                    full_text += post.text + " "
                                if post.reply_to_message:
                                    if post.reply_to_message.caption:
                                        full_text += post.reply_to_message.caption + " "
                                    if post.reply_to_message.text:
                                        full_text += post.reply_to_message.text + " "
                                
                                # استخراج الرقم
                                ep = extract_ep_num_simple(full_text)
                                if ep > 0:
                                    return ep
            except:
                continue
    except Exception as e:
        logging.error(f"خطأ في get_episode_from_channels: {e}")
    
    return 0

# ===== [6] دالة عرض الحلقة =====
async def show_episode(client, message, v_id):
    try:
        db_data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            return await message.reply_text("❌ حدث خطأ غير متوقع")
        
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

# ===== [7] أمر البدء الذكي =====
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
        db_data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            waiting_msg = await message.reply_text("🔄 جاري تحضير الحلقة...")
            
            try:
                source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                
                if source_msg and (source_msg.caption or source_msg.text):
                    raw_text = source_msg.caption or source_msg.text
                    
                    # محاولة استخراج من التنسيق الجديد أولاً
                    title, ep_num = extract_title_and_episode(raw_text)
                    
                    if not title:
                        title = raw_text.split('\n')[0][:100]
                    
                    if ep_num == 0:
                        # البحث في قنوات النشر
                        ep_num = await get_episode_from_channels(client, v_id)
                    
                    if ep_num == 0:
                        await waiting_msg.edit_text(
                            f"⚠️ لم أجد رقم الحلقة\n"
                            f"المسلسل: {title}\n"
                            f"الرجاء استخدام: /add {v_id} رقم_الحلقة {title}"
                        )
                        return
                    
                    db_query("""
                        INSERT INTO videos (v_id, title, ep_num, status) 
                        VALUES (%s, %s, %s, 'posted')
                        ON CONFLICT (v_id) DO UPDATE SET 
                        title = EXCLUDED.title,
                        ep_num = EXCLUDED.ep_num
                    """, (v_id, title, ep_num), fetch=False)
                    
                    await waiting_msg.delete()
                    await show_episode(client, message, v_id)
                else:
                    await waiting_msg.edit_text("❌ الحلقة غير موجودة")
                    
            except Exception as e:
                await waiting_msg.edit_text(f"❌ خطأ: {e}")
        else:
            await show_episode(client, message, v_id)
    else:
        welcome_text = """👋 **أهلاً بك في بوت المشاهدة الذكي**

📺 **طريقة العمل:**
1. اكتب في وصف الفيديو: "اسم المسلسل رقم_الحلقة"
2. استخدم /scan_source لتحديث كل الحلقات

🆘 @Mohsen_7e"""
        await message.reply_text(welcome_text)

# ===== [8] أمر التحكم في الأزرار =====
@app.on_message(filters.command("toggle_buttons") & filters.user(ADMIN_ID))
async def toggle_buttons(client, message):
    global SHOW_MORE_BUTTONS
    SHOW_MORE_BUTTONS = not SHOW_MORE_BUTTONS
    status = "✅ مفعلة" if SHOW_MORE_BUTTONS else "❌ معطلة"
    await message.reply_text(f"أزرار المزيد: {status}")

# ===== [9] الأمر الرئيسي لتحديث قاعدة البيانات =====
@app.on_message(filters.command("scan_source") & filters.user(ADMIN_ID))
async def scan_source_command(client, message):
    msg = await message.reply_text("🔄 جاري فحص قناة المصدر...")
    
    stats = {
        'scanned': 0,
        'updated': 0,
        'errors': 0
    }
    
    try:
        async for post in client.get_chat_history(SOURCE_CHANNEL, limit=500):
            stats['scanned'] += 1
            
            try:
                if not (post.caption or post.text):
                    continue
                    
                raw_text = post.caption or post.text
                v_id = str(post.id)
                
                # محاولة استخراج من التنسيق الجديد أولاً
                title, ep_num = extract_title_and_episode(raw_text)
                
                if not title:
                    title = raw_text.split('\n')[0][:100]
                
                if ep_num == 0:
                    # البحث في قنوات النشر
                    ep_num = await get_episode_from_channels(client, v_id)
                
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
                logging.error(f"خطأ: {e}")
            
            if stats['updated'] % 50 == 0 and stats['updated'] > 0:
                await msg.edit_text(f"🔄 تم تحديث {stats['updated']} حلقة...")
    
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")
        return
    
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    result = f"""✅ **تم التحديث**

📊 **الإحصائيات:**
• رسائل ممسوحة: {stats['scanned']}
• حلقات محدثة: {stats['updated']}
• أخطاء: {stats['errors']}

📁 إجمالي الحلقات: {total}
🔘 أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}"""
    await msg.edit_text(result)

# ===== [10] أمر إضافة حلقة يدوياً =====
@app.on_message(filters.command("add") & filters.user(ADMIN_ID))
async def add_episode(client, message):
    command = message.text.split()
    if len(command) < 3:
        return await message.reply_text("❌ استخدم: /add المعرف رقم_الحلقة اسم_المسلسل")
    
    v_id = command[1]
    ep_num = int(command[2])
    title = ' '.join(command[3:])
    
    try:
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not source_msg:
            return await message.reply_text("❌ الحلقة غير موجودة")
        
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status) 
            VALUES (%s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num
        """, (v_id, title, ep_num), fetch=False)
        
        await message.reply_text(f"✅ تمت الإضافة\n{title} - حلقة {ep_num}")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [11] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def smart_stats(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    views = db_query("SELECT COUNT(*) FROM views_log")[0][0]
    
    top_series = db_query("""
        SELECT title, COUNT(*) as eps 
        FROM videos 
        GROUP BY title 
        ORDER BY eps DESC 
        LIMIT 10
    """)
    
    text = f"🤖 **الإحصائيات**\n\n"
    text += f"📁 الحلقات: {total}\n"
    text += f"👥 المستخدمين: {users}\n"
    text += f"👀 المشاهدات: {views}\n"
    text += f"🔘 أزرار المزيد: {'مفعلة' if SHOW_MORE_BUTTONS else 'معطلة'}\n\n"
    text += "📊 **أكثر 10 مسلسلات:**\n"
    
    for title, count in top_series:
        text += f"• {title}: {count} حلقة\n"
    
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
            return await message.reply_text("❌ غير موجودة")
        
        raw_text = source_msg.caption or source_msg.text or ""
        
        # محاولة استخراج من التنسيق الجديد
        title, ep_num = extract_title_and_episode(raw_text)
        
        if not title:
            title = raw_text.split('\n')[0][:100]
        
        if ep_num == 0:
            ep_num = await get_episode_from_channels(client, v_id)
        
        if ep_num == 0:
            return await message.reply_text(f"⚠️ لم أجد الرقم، استخدم /add {v_id} رقم_الحلقة {title}")
        
        db_query("""
            INSERT INTO videos (v_id, title, ep_num, status) 
            VALUES (%s, %s, %s, 'posted')
            ON CONFLICT (v_id) DO UPDATE SET 
            title = EXCLUDED.title,
            ep_num = EXCLUDED.ep_num
        """, (v_id, title, ep_num), fetch=False)
        
        await message.reply_text(f"✅ تم الإصلاح\n{title} - حلقة {ep_num}")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [13] إنشاء الجداول =====
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
    
    print("✅ تم إنشاء الجداول")

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
