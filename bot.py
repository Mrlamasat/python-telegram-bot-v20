import os
import psycopg2
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageIdInvalid

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

# ===== دالة التحقق من صحة الفيديو في القناة =====
async def is_valid_video(client, v_id):
    try:
        await client.get_messages(SOURCE_CHANNEL, int(v_id))
        return True
    except:
        return False

# ===== معالج بدء البوت =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        if len(message.command) > 1:
            v_id = message.command[1]
            
            # التحقق من صحة الفيديو قبل العرض
            if not await is_valid_video(client, v_id):
                return await message.reply_text("⚠️ هذه الحلقة غير متوفرة حالياً")
            
            await show_episode(client, message, v_id)
        else:
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 قناة النشر", url=BACKUP_CHANNEL_LINK)
            ]])
            await message.reply_text(
                "👋 أهلاً بك في بوت المسلسلات!\n"
                "اختر حلقة من القناة للمشاهدة.",
                reply_markup=markup
            )
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.reply_text("حدث خطأ، حاول مرة أخرى")

# ===== دالة عرض الحلقة =====
async def show_episode(client, message, current_vid):
    # جلب معلومات الحلقة الحالية
    video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not video_info:
        return await message.reply_text("⚠️ هذه الحلقة غير موجودة في قاعدة البيانات")
    
    title, current_ep = video_info[0]
    
    # تحديث المشاهدات
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    # جلب جميع حلقات نفس المسلسل
    all_episodes = db_query("""
        SELECT v_id, ep_num FROM videos 
        WHERE title = %s AND status = 'posted' AND ep_num > 0 
        ORDER BY ep_num ASC
    """, (title,))
    
    # التحقق من صحة كل فيديو واختيار الأحدث لكل رقم حلقة
    valid_episodes = {}
    
    for vid, ep_num in all_episodes:
        # إذا لم نضف هذا الرقم بعد، أو وجدنا فيديو أحدث لهذا الرقم
        if ep_num not in valid_episodes:
            # تحقق من صحة الفيديو
            if await is_valid_video(client, vid):
                valid_episodes[ep_num] = vid
    
    # بناء أزرار الحلقات الصالحة فقط
    btns, row = [], []
    
    # ترتيب الأرقام تصاعدياً
    for ep_num in sorted(valid_episodes.keys()):
        vid = valid_episodes[ep_num]
        
        # تمييز الحلقة الحالية
        if str(vid) == str(current_vid):
            label = f"✅ {ep_num}"
        else:
            label = str(ep_num)
        
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
        
        if data.startswith("ep_"):
            v_id = data.replace("ep_", "")
            
            # التحقق من صحة الفيديو قبل العرض
            if not await is_valid_video(client, v_id):
                await callback_query.answer("❌ هذه الحلقة غير متوفرة", show_alert=True)
                return
            
            # حذف الرسالة القديمة
            await callback_query.message.delete()
            
            # عرض الحلقة الجديدة
            await show_episode(client, callback_query.message, v_id)
            
            await callback_query.answer()
            
    except Exception as e:
        logging.error(f"Callback error: {e}")
        await callback_query.answer("حدث خطأ", show_alert=True)

# ===== أوامر المدير =====
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

@app.on_message(filters.command("clean") & filters.private)
async def clean_command(client, message):
    """أمر لتنظيف قاعدة البيانات من الإدخالات المكررة والمعطلة (للمدير فقط)"""
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط.")
    
    status_msg = await message.reply_text("🧹 جاري تنظيف قاعدة البيانات...")
    
    # جلب جميع الفيديوهات
    all_videos = db_query("SELECT v_id, title, ep_num FROM videos WHERE status = 'posted'")
    
    cleaned = 0
    deleted = 0
    valid_eps = {}
    
    for v_id, title, ep_num in all_videos:
        if not title or not ep_num:
            continue
            
        # التحقق من صحة الفيديو
        if await is_valid_video(client, v_id):
            key = f"{title}_{ep_num}"
            # إذا كان هذا الرقم موجوداً مسبقاً، احتفظ بالأحدث (بأكبر v_id)
            if key not in valid_eps or int(v_id) > int(valid_eps[key]):
                if key in valid_eps:
                    # حذف القديم
                    db_query("DELETE FROM videos WHERE v_id = %s", (valid_eps[key],), fetch=False)
                    deleted += 1
                valid_eps[key] = v_id
            else:
                # حذف المكرر الأقدم
                db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
                deleted += 1
        else:
            # حذف الفيديو المعطل
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            deleted += 1
        
        cleaned += 1
    
    await status_msg.edit_text(f"✅ تم التنظيف!\n• تم فحص {cleaned} إدخال\n• تم حذف {deleted} إدخال مكرر/معطل")

# ===== معالج قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        logging.info(f"📥 رسالة جديدة - ID: {message.id}, Type: {message.media}")
        
        if message.video or message.document:
            v_id = str(message.id)
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting')", (v_id,), fetch=False)
            
            await message.reply_text(
                "✅ تم استلام الفيديو!\n📌 أرسل الآن البوستر مع اسم المسلسل:"
            )
        
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
        
        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await message.reply_text("❌ لا يوجد فيديو في انتظار رقم الحلقة.")
                return
            
            v_id, title, p_id = res[0]
            ep_num = int(message.text)
            
            # حذف أي إدخال سابق بنفس العنوان ورقم الحلقة
            db_query("DELETE FROM videos WHERE title = %s AND ep_num = %s AND v_id != %s", 
                    (title, ep_num, v_id), fetch=False)
            
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
