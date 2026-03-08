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
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            series_name TEXT,
            ep_num INTEGER DEFAULT 0,
            encrypted_name TEXT,
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    
    db_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    print("✅ قاعدة البيانات جاهزة")

# ===== [5] دوال الاستخراج المحسنة =====
def extract_episode_number(text):
    if not text:
        return 0
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else 0

def extract_series_name(text):
    """استخراج اسم المسلسل مع تنظيف أفضل"""
    if not text:
        return "غير معروف"
    
    # إزالة الأرقام من النهاية
    clean = re.sub(r'\s*\d+\s*$', '', text.strip())
    clean = re.sub(r'^\d+\s*', '', clean)
    
    # إزالة الرموز الخاصة
    clean = re.sub(r'[^\w\s]', '', clean)
    
    # تنظيف المسافات الزائدة
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    if not clean or len(clean) < 2:
        return "غير معروف"
    
    return clean[:50]

def extract_series_from_video(text, v_id):
    """استخراج اسم المسلسل مع استخدام v_id كبديل"""
    series = extract_series_name(text)
    if series == "غير معروف":
        # استخدام آخر 3 أرقام من v_id كاسم مؤقت
        return f"مسلسل {v_id[-3:]}"
    return series

# ===== [6] دالة أزرار الحلقات =====
def get_episode_buttons(series_name, current_id, bot_user):
    if not series_name or series_name == "غير معروف":
        return []
    
    eps = db_query("""
        SELECT ep_num, v_id FROM videos 
        WHERE series_name = %s 
        ORDER BY ep_num ASC LIMIT 50
    """, (series_name,))
    
    if not eps or len(eps) < 2:  # تحتاج على الأقل حلقتين
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

# ===== [7] أمر إصلاح شامل =====
@app.on_message(filters.command("fix_all") & filters.user(ADMIN_ID))
async def fix_all(client, message):
    msg = await message.reply_text("🔄 جاري الإصلاح الشامل...")
    
    # 1️⃣ إصلاح الفيديوهات التي ليس لها اسم مسلسل
    videos = db_query("SELECT v_id FROM videos WHERE series_name IS NULL OR series_name = '' OR series_name = 'None'")
    fixed = 0
    
    for (v_id,) in videos:
        try:
            source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if source and source.video:
                series = extract_series_from_video(source.caption or "", v_id)
                ep = extract_episode_number(source.caption or "")
                if ep == 0:
                    ep = 1
                
                db_query("""
                    UPDATE videos 
                    SET series_name = %s, ep_num = %s 
                    WHERE v_id = %s
                """, (series, ep, v_id), fetch=False)
                fixed += 1
        except:
            continue
    
    await msg.edit_text(f"✅ تم إصلاح {fixed} فيديو")
    
    # 2️⃣ عرض إحصائيات بعد الإصلاح
    stats = db_query("""
        SELECT series_name, COUNT(*) as count 
        FROM videos 
        GROUP BY series_name 
        ORDER BY count DESC 
        LIMIT 10
    """)
    
    result = "📊 **الإحصائيات بعد الإصلاح:**\n\n"
    for name, count in stats:
        result += f"• {name}: {count} حلقة\n"
    
    await message.reply_text(result)

# ===== [8] أمر إصلاح حلقة محددة =====
@app.on_message(filters.command("fix_one") & filters.user(ADMIN_ID))
async def fix_one(client, message):
    cmd = message.text.split()
    if len(cmd) < 2:
        await message.reply_text("❌ استخدم: /fix_one v_id")
        return
    
    v_id = cmd[1]
    
    try:
        source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if not source or not source.video:
            return await message.reply_text("❌ الفيديو غير موجود")
        
        series = extract_series_from_video(source.caption or "", v_id)
        ep = extract_episode_number(source.caption or "")
        if ep == 0:
            ep = 1
        
        db_query("""
            INSERT INTO videos (v_id, series_name, ep_num) 
            VALUES (%s, %s, %s)
            ON CONFLICT (v_id) DO UPDATE SET 
            series_name = EXCLUDED.series_name,
            ep_num = EXCLUDED.ep_num
        """, (v_id, series, ep), fetch=False)
        
        await message.reply_text(f"✅ تم إصلاح الحلقة {v_id}\nالمسلسل: {series}\nرقم الحلقة: {ep}")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [9] أمر البدء =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query(
        "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_seen = CURRENT_TIMESTAMP",
        (message.from_user.id, message.from_user.username or ""),
        fetch=False
    )
    
    if len(message.command) > 1:
        v_id = message.command[1]
        me = await client.get_me()
        
        data = db_query("SELECT series_name, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and source.video:
                    series = extract_series_from_video(source.caption or "", v_id)
                    ep = extract_episode_number(source.caption or "")
                    if ep == 0:
                        ep = 1
                    
                    db_query("""
                        INSERT INTO videos (v_id, series_name, ep_num) 
                        VALUES (%s, %s, %s) ON CONFLICT (v_id) DO NOTHING
                    """, (v_id, series, ep), fetch=False)
                    
                    current_series, current_ep = series, ep
                else:
                    return await message.reply_text("❌ لم يتم العثور على الفيديو.")
            except Exception as e:
                return await message.reply_text(f"⚠️ خطأ: {e}")
        else:
            current_series, current_ep = data[0]
            if not current_series or current_series == "None":
                # محاولة إصلاح تلقائي
                try:
                    source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                    if source and source.video:
                        current_series = extract_series_from_video(source.caption or "", v_id)
                        db_query("UPDATE videos SET series_name = %s WHERE v_id = %s", 
                                (current_series, v_id), fetch=False)
                except:
                    current_series = "غير معروف"

        # توليد الأزرار
        keyboard = []
        if SHOW_MORE_BUTTONS and current_series != "غير معروف":
            more_buttons = get_episode_buttons(current_series, v_id, me.username)
            if more_buttons:
                keyboard.extend(more_buttons)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=f"<b>🎬 {current_series} - الحلقة {current_ep}</b>",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
        
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        await message.reply_text("👋 أهلاً بك في بوت المشاهدة.")

# ===== [10] أمر الإحصائيات =====
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

# ===== [11] أمر تشخيص =====
@app.on_message(filters.command("debug") & filters.user(ADMIN_ID))
async def debug_cmd(client, message):
    cmd = message.text.split()
    if len(cmd) < 2:
        await message.reply_text("❌ استخدم: /debug v_id")
        return
    
    v_id = cmd[1]
    
    current = db_query("SELECT series_name, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not current:
        await message.reply_text("❌ الحلقة غير موجودة في قاعدة البيانات")
        return
    
    series, ep = current[0]
    
    others = db_query("""
        SELECT COUNT(*) FROM videos 
        WHERE series_name = %s AND v_id != %s
    """, (series, v_id))
    
    count = others[0][0] if others else 0
    
    text = f"🔍 **تشخيص الحلقة {v_id}**\n\n"
    text += f"📌 المسلسل: {series}\n"
    text += f"🔢 رقم الحلقة: {ep}\n"
    text += f"📊 عدد الحلقات الأخرى: {count}\n"
    text += f"⚙️ أزرار المزيد: {'✅ ستعمل' if count > 0 and SHOW_MORE_BUTTONS else '❌ لن تعمل'}\n"
    
    if series == "غير معروف" or series == "None":
        text += "\n⚠️ المشكلة: اسم المسلسل غير صحيح!\n"
        text += "استخدم /fix_one " + v_id + " لإصلاحها"
    
    await message.reply_text(text)

# ===== [12] أمر اختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [13] التشغيل =====
def main():
    print("🚀 تشغيل البوت...")
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
