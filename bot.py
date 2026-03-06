import os
import psycopg2
import re
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
    logging.info("✅ قاعدة البيانات جاهزة")

# ===== دوال مساعدة =====
def encrypt_title(title):
    if not title:
        return "مسلسل"
    if len(title) <= 6:
        return title
    return title[:3] + "..." + title[-3:]

async def get_bot_username():
    me = await app.get_me()
    return me.username

# ===== دالة التحقق من صحة الفيديو في قناة المصدر =====
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
    # 1. جلب معلومات الحلقة المطلوبة
    video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not video_info:
        return await message.reply_text("⚠️ هذه الحلقة غير موجودة في قاعدة البيانات")
    
    title, current_ep = video_info[0]
    clean_title = title.strip()
    
    # تحديث المشاهدات
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    # 2. جلب جميع الحلقات المنشورة لهذا المسلسل
    all_episodes = db_query("""
        SELECT v_id, ep_num FROM videos 
        WHERE TRIM(title) = %s AND status = 'posted' AND ep_num > 0 
        ORDER BY ep_num ASC
    """, (clean_title,))
    
    # 3. بناء الأزرار (فقط للحلقات الصالحة)
    username = await get_bot_username()
    btns, row = [], []
    seen_eps = set()  # لمنع التكرار

    for vid, ep_num in all_episodes:
        # تحقق من صحة الفيديو في قناة المصدر
        if not await is_valid_video(client, vid):
            continue  # تخطي هذا الإدخال إذا كان الفيديو غير صالح
            
        if ep_num in seen_eps:
            continue
        seen_eps.add(ep_num)

        # تمييز الحلقة الحالية
        label = f"✅ {ep_num}" if str(vid) == str(current_vid) else str(ep_num)
        
        row.append(InlineKeyboardButton(
            label, 
            url=f"https://t.me/{username}?start={vid}"
        ))
        
        if len(row) == 5:
            btns.append(row)
            row = []
    
    if row:
        btns.append(row)
    
    # إضافة زر القناة الاحتياطية
    btns.append([InlineKeyboardButton("📢 قناة النشر الأساسية", url=BACKUP_CHANNEL_LINK)])
    
    # 4. إرسال الفيديو مع الأزرار
    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(current_vid),
            caption=f"<b>📺 {encrypt_title(title)} - حلقة {current_ep}</b>",
            reply_markup=InlineKeyboardMarkup(btns),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Copy Error: {e}")
        await message.reply_text("⚠️ عذراً، تعذر جلب الفيديو من المصدر.")

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

# ===== أمر حذف الإدخالات غير الصالحة من قاعدة البيانات فقط =====
@app.on_message(filters.command("fix") & filters.private)
async def fix_invalid_entries(client, message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔍 جاري البحث عن الإدخالات غير الصالحة...")
    
    # جلب جميع الإدخالات من قاعدة البيانات
    all_entries = db_query("SELECT v_id, title, ep_num FROM videos WHERE status = 'posted'")
    
    invalid_count = 0
    valid_count = 0
    invalid_list = []
    
    for v_id, title, ep_num in all_entries:
        # التحقق من صحة الفيديو في قناة المصدر
        if not await is_valid_video(client, v_id):
            # هذا الإدخال غير صالح (لا يوجد فيديو في القناة)
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            invalid_count += 1
            invalid_list.append(f"• {title} - حلقة {ep_num} (ID: {v_id})")
        else:
            valid_count += 1
    
    # تقرير النتيجة
    if invalid_count > 0:
        report = f"✅ **تم الحذف بنجاح!**\n\n"
        report += f"📊 **الإحصائيات:**\n"
        report += f"• إجمالي الإدخالات: {valid_count + invalid_count}\n"
        report += f"• الإدخالات الصالحة: {valid_count}\n"
        report += f"• الإدخالات غير الصالحة: {invalid_count}\n\n"
        report += f"🗑️ **الإدخالات المحذوفة:**\n"
        report += "\n".join(invalid_list[:10])  # عرض أول 10 فقط
        if len(invalid_list) > 10:
            report += f"\n... و{len(invalid_list) - 10} إدخالات أخرى"
    else:
        report = f"✅ **لا توجد إدخالات غير صالحة!**\n\n"
        report += f"📊 جميع الإدخالات الـ {valid_count} صالحة."
    
    await status_msg.edit_text(report)

# ===== أمر المزامنة مع قناة النشر =====
@app.on_message(filters.command("sync") & filters.private)
async def sync_from_channel(client, message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔄 جاري مطابقة البيانات مع قناة النشر... انتظر قليلاً")
    
    updated = 0
    processed = 0
    
    # جلب آخر 200 رسالة من قناة النشر العامة
    async for msg in client.get_chat_history(PUBLIC_POST_CHANNEL, limit=200):
        processed += 1
        
        # التأكد أنها رسالة تحتوي على زر (رابط start) ووصف
        if msg.reply_markup and msg.caption and msg.reply_markup.inline_keyboard:
            try:
                # استخراج v_id من رابط الزر
                button_url = msg.reply_markup.inline_keyboard[0][0].url
                if "start=" not in button_url:
                    continue
                    
                v_id = button_url.split("start=")[1]
                
                # استخراج رقم الحلقة من الوصف
                patterns = [
                    r'\[(\d+)\]',  # [17]
                    r'حلقة:?\s*(\d+)',  # حلقة 17
                    r'الحلقة:?\s*(\d+)'  # الحلقة 17
                ]
                
                correct_ep = None
                for pattern in patterns:
                    match = re.search(pattern, msg.caption, re.IGNORECASE)
                    if match:
                        correct_ep = int(match.group(1))
                        break
                
                if correct_ep:
                    # تحقق مما إذا كان هذا v_id موجود في قاعدة البيانات
                    existing = db_query("SELECT ep_num FROM videos WHERE v_id = %s", (v_id,))
                    
                    if existing:
                        # إذا كان موجوداً ولكن برقم مختلف
                        if existing[0][0] != correct_ep:
                            db_query(
                                "UPDATE videos SET ep_num = %s, status = 'posted' WHERE v_id = %s",
                                (correct_ep, v_id),
                                fetch=False
                            )
                            updated += 1
                    else:
                        # إذا لم يكن موجوداً، أضفه
                        title_match = re.search(r'<b>(.+?)</b>', msg.caption)
                        title = title_match.group(1) if title_match else "مسلسل"
                        title = re.sub(r'<[^>]+>', '', title)
                        
                        db_query(
                            "INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted')",
                            (v_id, title, correct_ep),
                            fetch=False
                        )
                        updated += 1
                        
            except Exception as e:
                logging.error(f"Error syncing msg {msg.id}: {e}")
    
    await status_msg.edit_text(
        f"✅ **تمت المزامنة بنجاح!**\n\n"
        f"📊 **الإحصائيات:**\n"
        f"• تم فحص {processed} منشور في القناة\n"
        f"• تم تحديث/إضافة {updated} حلقة\n\n"
        f"🔹 استخدم أمر /fix لحذف الإدخالات غير الصالحة."
    )

# ===== معالج قناة المصدر (لرفع الفيديوهات) =====
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
            username = await get_bot_username()
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
