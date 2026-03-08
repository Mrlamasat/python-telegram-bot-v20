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

app = Client("railway_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] كلمات عشوائية للتشفير =====
ENCRYPTION_WORDS = ["حصري", "جديد", "متابعة", "الان", "مميز", "شاهد", "حلقة", "مسلسل"]

def encrypt_title(title, level="HIGH"):
    """تشفير اسم المسلسل بالكامل"""
    if not title:
        return "محتوى"
    
    if level == "HIGH":
        # إخفاء تام - كلمات عشوائية
        words = title.split()
        if len(words) > 1:
            # أخذ كلمة عشوائية من العنوان وتشفيرها
            word = random.choice(words)
            # قلب الكلمة
            reversed_word = word[::-1]
            return f"🎬 {reversed_word} {random.randint(10,99)}"
        else:
            # عنوان قصير - قلب كامل
            return f"🎬 {title[::-1][:10]} {random.randint(10,99)}"
    
    return title

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

# ===== [4] دالة استخراج البيانات =====
def extract_info(text):
    """استخراج اسم المسلسل ورقم الحلقة"""
    if not text:
        return "فيديو", 0
    
    first_line = text.strip().split('\n')[0]
    
    # البحث عن نمط "المداح 13"
    match = re.search(r'^(.+?)\s+(\d+)$', first_line)
    if match:
        title = match.group(1).strip()
        ep = int(match.group(2))
        return title, ep
    
    # البحث عن أي رقم
    nums = re.findall(r'\d+', first_line)
    if nums:
        return first_line, int(nums[0])
    
    return first_line[:50], 1

# ===== [5] أمر الاختبار =====
@app.on_message(filters.command("test") & filters.private)
async def test_cmd(client, message):
    await message.reply_text("✅ البوت يعمل!")

# ===== [6] أمر البدء الذكي =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    # تسجيل المستخدم
    db_query(
        "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_seen = CURRENT_TIMESTAMP",
        (message.from_user.id, message.from_user.username or ""),
        fetch=False
    )
    
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # البحث في قاعدة البيانات
        data = db_query("SELECT title, encrypted_title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not data:
            msg = await message.reply_text("🔄 جاري التحميل...")
            try:
                source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                if source and source.video:
                    text = source.caption or ""
                    title, ep = extract_info(text)
                    encrypted = encrypt_title(title)
                    
                    # حفظ في قاعدة البيانات
                    db_query(
                        "INSERT INTO videos (v_id, title, encrypted_title, ep_num) VALUES (%s, %s, %s, %s)",
                        (v_id, title, encrypted, ep),
                        fetch=False
                    )
                    
                    await msg.delete()
                    
                    # عرض الحلقة في البوت (بدون اسم)
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)
                    ]])
                    
                    await client.copy_message(
                        message.chat.id,
                        SOURCE_CHANNEL,
                        int(v_id),
                        caption=f"<b>🎬 الحلقة {ep}</b>",
                        reply_markup=keyboard
                    )
                    
                    db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
                else:
                    await msg.edit_text("❌ الحلقة غير موجودة")
            except Exception as e:
                await msg.edit_text(f"❌ خطأ: {e}")
        else:
            title, encrypted, ep = data[0]
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)
            ]])
            
            await client.copy_message(
                message.chat.id,
                SOURCE_CHANNEL,
                int(v_id),
                caption=f"<b>🎬 الحلقة {ep}</b>",
                reply_markup=keyboard
            )
            
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    else:
        await message.reply_text("👋 بوت المشاهدة الآمن")

# ===== [7] أمر النشر في القناة =====
@app.on_message(filters.command("publish") & filters.user(ADMIN_ID))
async def publish_cmd(client, message):
    cmd = message.text.split()
    if len(cmd) < 3:
        await message.reply_text("❌ استخدم: /ublish v_id ep_num")
        return
    
    v_id = cmd[1]
    ep = int(cmd[2])
    
    try:
        source = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if source and source.video:
            text = source.caption or ""
            title, _ = extract_info(text)
            encrypted = encrypt_title(title)
            
            # حفظ في قاعدة البيانات
            db_query(
                "INSERT INTO videos (v_id, title, encrypted_title, ep_num) VALUES (%s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET ep_num = %s",
                (v_id, title, encrypted, ep, ep),
                fetch=False
            )
            
            # رابط البوت
            me = await client.get_me()
            bot_link = f"https://t.me/{me.username}?start={v_id}"
            
            button = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 مشاهدة الحلقة", url=bot_link)
            ]])
            
            # نشر في القناة (باسم مشفر)
            await client.send_photo(
                PUBLISH_CHANNEL,
                "https://telegra.ph/file/placeholder.jpg",  # ضع رابط صورة افتراضية
                caption=f"{encrypted}\nالحلقة {ep}",
                reply_markup=button
            )
            
            await message.reply_text(f"✅ تم النشر: {encrypted} - حلقة {ep}")
        else:
            await message.reply_text("❌ الفيديو غير موجود")
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== [8] أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats_cmd(client, message):
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    users = db_query("SELECT COUNT(*) FROM users")[0][0]
    
    top = db_query("""
        SELECT encrypted_title, views FROM videos 
        WHERE views > 0 
        ORDER BY views DESC 
        LIMIT 5
    """)
    
    text = f"📊 **الإحصائيات**\n\n"
    text += f"📁 الحلقات: {total}\n"
    text += f"👥 المستخدمين: {users}\n\n"
    text += "🏆 **الأكثر مشاهدة:**\n"
    
    for title, views in top:
        text += f"• {title}: {views} مشاهدة\n"
    
    await message.reply_text(text)

# ===== [9] مراقبة التعديلات =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
async def on_edit(client, message):
    if message.video and message.caption:
        v_id = str(message.id)
        title, ep = extract_info(message.caption)
        encrypted = encrypt_title(title)
        
        db_query(
            "UPDATE videos SET title = %s, encrypted_title = %s, ep_num = %s WHERE v_id = %s",
            (title, encrypted, ep, v_id),
            fetch=False
        )
        logging.info(f"✅ تحديث الحلقة {v_id} → {ep}")

# ===== [10] أمر اختبار التشفير =====
@app.on_message(filters.command("encrypt") & filters.user(ADMIN_ID))
async def encrypt_cmd(client, message):
    cmd = message.text.split(maxsplit=1)
    if len(cmd) < 2:
        await message.reply_text("❌ استخدم: /encrypt اسم المسلسل")
        return
    
    name = cmd[1]
    encrypted = encrypt_title(name)
    await message.reply_text(f"🔐 **الاسم الأصلي:** {name}\n🔒 **بعد التشفير:** {encrypted}")

# ===== [11] التشغيل =====
def main():
    print("🚀 تشغيل البوت الآمن...")
    
    try:
        app.run()
    except FloodWait as e:
        print(f"⏳ انتظر {e.value} ثانية")
        time.sleep(e.value)
    except Exception as e:
        print(f"❌ خطأ: {e}")

if __name__ == "__main__":
    main()
