import os
import psycopg2
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_stable", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=10)
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"Database Error: {e}")
        return []

def init_database():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            ep_num INTEGER,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            last_view TIMESTAMP
        )
    """, fetch=False)

# ===== دوال مساعدة =====
def encrypt_title(title):
    if not title:
        return "مسلسل"
    if len(title) <= 6:
        return title
    return title[:3] + "..." + title[-3:]

async def is_valid_video(client, v_id):
    """التحقق من وجود الفيديو في قناة المصدر"""
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        return msg and not msg.empty
    except:
        return False

# ===== معالج بدء البوت (عبر الرابط) =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        # إذا كان هناك معرف حلقة في الرابط
        if len(message.command) > 1:
            v_id = message.command[1]
            await show_episode(client, message, v_id)
        else:
            # رسالة ترحيب
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 قناة النشر", url=BACKUP_CHANNEL_LINK)
            ]])
            await message.reply_text(
                "👋 أهلاً بك في بوت المسلسلات!\n"
                "اختر حلقة من القناة للمشاهدة.",
                reply_markup=markup
            )
    except Exception as e:
        logging.error(f"Error in start: {e}")
        await message.reply_text("حدث خطأ، حاول مرة أخرى.")

# ===== دالة عرض الحلقة =====
async def show_episode(client, message, current_vid):
    # جلب معلومات الحلقة الحالية
    video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not video_info:
        await message.reply_text("⚠️ هذه الحلقة غير موجودة")
        return
    
    title, current_ep = video_info[0]
    
    # تحديث المشاهدات
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    # جلب جميع حلقات نفس المسلسل
    episodes = db_query("""
        SELECT v_id, ep_num FROM videos 
        WHERE title = %s AND status = 'posted' AND ep_num > 0 
        ORDER BY ep_num ASC
    """, (title,))
    
    # بناء أزرار الحلقات
    btns, row = [], []
    for vid, ep in episodes:
        # تمييز الحلقة الحالية بعلامة ✅
        if str(vid) == str(current_vid):
            label = f"✅ {ep}"
        else:
            label = str(ep)
        
        # استخدام callback_data بدلاً من url
        row.append(InlineKeyboardButton(label, callback_data=f"ep_{vid}"))
        
        if len(row) == 5:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    
    # إضافة زر القناة
    btns.append([InlineKeyboardButton("📢 قناة النشر", url=BACKUP_CHANNEL_LINK)])
    
    # إرسال الفيديو
    await client.copy_message(
        chat_id=message.chat.id,
        from_chat_id=SOURCE_CHANNEL,
        message_id=int(current_vid),
        caption=f"<b>📺 {encrypt_title(title)} - حلقة {current_ep}</b>",
        reply_markup=InlineKeyboardMarkup(btns),
        parse_mode=ParseMode.HTML
    )

# ===== معالج الضغط على الأزرار =====
@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    try:
        data = callback_query.data
        
        # إذا كان الضغط على زر حلقة
        if data.startswith("ep_"):
            v_id = data.replace("ep_", "")
            
            # التحقق من وجود الفيديو قبل العرض
            if not await is_valid_video(client, v_id):
                await callback_query.answer("❌ هذه الحلقة غير متوفرة (سيتم حذفها قريباً)", show_alert=True)
                return
            
            # حذف الرسالة القديمة
            await callback_query.message.delete()
            
            # عرض الحلقة الجديدة في نفس المحادثة
            await show_episode(client, callback_query.message, v_id)
            
            # إغلاق callback
            await callback_query.answer()
            
    except Exception as e:
        logging.error(f"Error in callback: {e}")
        await callback_query.answer("حدث خطأ", show_alert=True)

# ===== أوامر المدير =====

@app.on_message(filters.command("fix") & filters.private)
async def fix_command(client, message):
    """أمر حذف الإدخالات التي لا تحتوي على فيديوهات"""
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔍 جاري البحث عن الإدخالات غير الصالحة...")
    
    # جلب جميع الإدخالات
    all_entries = db_query("SELECT v_id, title, ep_num FROM videos WHERE status = 'posted'")
    
    deleted = 0
    invalid_list = []
    
    for v_id, title, ep_num in all_entries:
        # التحقق من وجود الفيديو في المصدر
        if not await is_valid_video(client, v_id):
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            deleted += 1
            if len(invalid_list) < 10:
                invalid_list.append(f"• {encrypt_title(title)} - حلقة {ep_num}")
    
    if deleted > 0:
        report = f"✅ **تم الحذف بنجاح!**\n\n"
        report += f"📊 **الإحصائيات:**\n"
        report += f"• تم حذف {deleted} إدخال لا يحتوي على فيديو\n\n"
        
        if invalid_list:
            report += "**المحذوفات:**\n" + "\n".join(invalid_list)
            if deleted > 10:
                report += f"\n... و{deleted - 10} إدخالات أخرى"
    else:
        report = f"✅ **لا توجد إدخالات غير صالحة!**\n\n"
        report += f"📊 جميع الإدخالات الـ {len(all_entries)} تحتوي على فيديوهات."
    
    await status_msg.edit_text(report)

@app.on_message(filters.command("check") & filters.private)
async def check_command(client, message):
    """أمر لعرض الإدخالات غير الصالحة بدون حذفها"""
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔍 جاري فحص قاعدة البيانات...")
    
    all_entries = db_query("SELECT v_id, title, ep_num FROM videos WHERE status = 'posted'")
    
    valid = []
    invalid = []
    
    for v_id, title, ep_num in all_entries:
        if await is_valid_video(client, v_id):
            valid.append((v_id, title, ep_num))
        else:
            invalid.append((v_id, title, ep_num))
    
    report = f"📊 **تقرير الفحص**\n\n"
    report += f"✅ إجمالي الإدخالات: {len(all_entries)}\n"
    report += f"✅ صالحة: {len(valid)}\n"
    report += f"❌ غير صالحة: {len(invalid)}\n\n"
    
    if invalid:
        report += "**الإدخالات غير الصالحة (التي سيتم حذفها):**\n"
        for i, (v_id, title, ep_num) in enumerate(invalid[:10], 1):
            report += f"{i}. {encrypt_title(title)} - حلقة {ep_num}\n"
        if len(invalid) > 10:
            report += f"... و{len(invalid) - 10} إدخالات أخرى\n"
        report += "\nاستخدم /fix لحذفها"
    
    await status_msg.edit_text(report)

@app.on_message(filters.command("id") & filters.private)
async def id_command(client, message):
    await message.reply_text(f"معرفك: `{message.from_user.id}`")

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط.")
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    total_videos = db_query("SELECT COUNT(*) FROM videos")[0][0]
    total_views = db_query("SELECT SUM(views) FROM videos")[0][0] or 0
    unique_series = db_query("SELECT COUNT(DISTINCT title) FROM videos WHERE title IS NOT NULL")[0][0]
    
    # الأكثر مشاهدة اليوم
    today_views = db_query("""
        SELECT title, COUNT(*) as daily_views 
        FROM videos 
        WHERE last_view >= %s AND title IS NOT NULL
        GROUP BY title 
        ORDER BY daily_views DESC 
        LIMIT 5
    """, (today_start,))
    
    # أشهر 5 مسلسلات
    top_series = db_query("""
        SELECT title, SUM(views) as total_views 
        FROM videos 
        WHERE title IS NOT NULL 
        GROUP BY title 
        ORDER BY total_views DESC 
        LIMIT 5
    """)
    
    text = "📊 **إحصائيات البوت**\n\n"
    text += f"**📌 إحصائيات عامة:**\n"
    text += f"• عدد المسلسلات: {unique_series}\n"
    text += f"• عدد الحلقات: {total_videos}\n"
    text += f"• إجمالي المشاهدات: {total_views:,}\n\n"
    
    if today_views:
        text += f"**🔥 الأكثر مشاهدة اليوم:**\n"
        for title, views in today_views:
            text += f"• {encrypt_title(title)} - {views} مشاهدة\n"
        text += "\n"
    
    if top_series:
        text += f"**🏆 الأكثر مشاهدة كل الوقت:**\n"
        for i, (title, views) in enumerate(top_series, 1):
            text += f"{i}. {encrypt_title(title)} - {views} مشاهدة\n"
    
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ===== معالج قناة المصدر (لرفع الفيديوهات) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        logging.info(f"📥 رسالة جديدة - ID: {message.id}, Type: {message.media}")
        
        # فيديو
        if message.video or message.document:
            v_id = str(message.id)
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting')", (v_id,), fetch=False)
            
            await message.reply_text(
                "✅ تم استلام الفيديو!\n📌 أرسل الآن البوستر مع اسم المسلسل:"
            )
        
        # بوستر
        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await message.reply_text("❌ لا يوجد فيديو في الانتظار. أرسل الفيديو أولاً.")
                return
            
            v_id = res[0][0]
            title = message.caption or "مسلسل"
            
            db_query(
                "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s",
                (title, message.photo.file_id, v_id),
                fetch=False
            )
            
            await message.reply_text(f"📌 تم حفظ البوستر لـ: {title}\n🔢 أرسل رقم الحلقة:")
        
        # رقم الحلقة
        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await message.reply_text("❌ لا يوجد فيديو في انتظار رقم الحلقة.")
                return
            
            v_id, title, p_id = res[0]
            ep_num = int(message.text)
            
            db_query(
                "UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s",
                (ep_num, v_id),
                fetch=False
            )
            
            # النشر في القناة العامة
            username = (await app.get_me()).username
            pub_caption = f"🎬 <b>{encrypt_title(title)}</b>\n\n<b>الحلقة: [{ep_num}]</b>"
            pub_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ مشاهدة", url=f"https://t.me/{username}?start={v_id}")
            ]])
            
            await client.send_photo(
                chat_id=PUBLIC_POST_CHANNEL,
                photo=p_id,
                caption=pub_caption,
                reply_markup=pub_markup
            )
            
            await message.reply_text(f"✅ تم النشر: {title} - حلقة {ep_num}")
    
    except Exception as e:
        logging.error(f"خطأ: {e}")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    init_database()
    logging.info("🚀 بدء التشغيل...")
    app.run()
