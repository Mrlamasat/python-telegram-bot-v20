import os
import psycopg2
import logging
from datetime import datetime, timedelta
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

# قاموس لتخزين حالة الفحص لكل مستخدم
user_check_state = {}

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

# ===== دوال مساعدة للتشفير =====

def encrypt_title(title, level=2):
    """
    تشفير اسم المسلسل بعدة مستويات - للمستخدمين العاديين فقط
    """
    if not title:
        return "مسلسل"
    
    title = title.strip()
    
    if len(title) <= 4:
        return title[:2] + "••"
    
    if level == 1:
        return title[:3] + "•••" + title[-3:]
    elif level == 2:
        chars_count = len(title.replace(" ", ""))
        return f"{title[:2]}••{chars_count}••{title[-2:]}"
    elif level == 3:
        first = title[0]
        last = title[-1]
        middle = len(title[1:-1].replace(" ", ""))
        return f"{first}••{middle}••{last}"
    else:
        return title[:2] + "•••" + title[-2:]

# ===== دوال مساعدة =====
def format_duration(seconds):
    """تنسيق المدة الزمنية"""
    if not seconds:
        return "غير معروف"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"

async def get_video_info(client, v_id):
    """استخراج معلومات الفيديو (المدة والجودة)"""
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if msg and msg.video:
            duration = msg.video.duration
            if msg.video.height >= 1080:
                quality = "Full HD"
            elif msg.video.height >= 720:
                quality = "HD"
            elif msg.video.height >= 480:
                quality = "SD"
            else:
                quality = "منخفضة"
            
            file_size = msg.video.file_size
            size_mb = file_size / (1024 * 1024)
            
            return {
                "duration": format_duration(duration),
                "quality": quality,
                "size": f"{size_mb:.1f} MB",
                "height": msg.video.height,
                "width": msg.video.width
            }
    except Exception as e:
        logging.error(f"Error getting video info: {e}")
    return None

async def is_valid_video(client, v_id):
    """التحقق من وجود الفيديو في قناة المصدر"""
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        return msg and not msg.empty
    except:
        return False

# ===== أمر اختبار القناة =====
@app.on_message(filters.command("test") & filters.private)
async def test_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔍 جاري اختبار الاتصال...")
    
    try:
        channel = await client.get_chat(SOURCE_CHANNEL)
        result = f"✅ **قناة المصدر:**\n"
        result += f"• الاسم: {channel.title}\n"
        result += f"• المعرف: {channel.id}\n"
        result += f"• النوع: {channel.type}\n\n"
        
        try:
            messages = []
            async for msg in client.get_chat_history(SOURCE_CHANNEL, limit=5):
                msg_type = "فيديو" if msg.video else "صورة" if msg.photo else "نص" if msg.text else "أخرى"
                messages.append(f"• ID: {msg.id} - النوع: {msg_type}")
            
            result += f"✅ **آخر 5 رسائل في القناة:**\n"
            result += "\n".join(messages) + "\n\n"
            
        except Exception as e:
            result += f"❌ **خطأ في جلب الرسائل:** {e}\n"
        
        me = await client.get_me()
        result += f"\n**معلومات البوت:**\n"
        result += f"• اليوزرنيم: @{me.username}\n"
        result += f"• المعرف: {me.id}\n"
        
        await status_msg.edit_text(result)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **خطأ في الوصول للقناة:** {e}")

# ===== معالج بدء البوت =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        if len(message.command) > 1:
            v_id = message.command[1]
            
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
        logging.error(f"Error in start: {e}")
        await message.reply_text("حدث خطأ، حاول مرة أخرى.")

# ===== دالة عرض الحلقة (مع تشفير الاسم للمستخدم العادي) =====
async def show_episode(client, message, current_vid):
    video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not video_info:
        await message.reply_text("⚠️ هذه الحلقة غير موجودة")
        return
    
    title, current_ep = video_info[0]
    
    # تحديث المشاهدات
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    # جلب معلومات الفيديو
    info = await get_video_info(client, current_vid)
    
    # للمستخدم العادي: تشفير الاسم
    encrypted_title = encrypt_title(title, level=3)
    
    info_text = f"<b>📺 {encrypted_title} - حلقة {current_ep}</b>\n\n"
    
    if info:
        info_text += f"⏱️ **المدة:** {info['duration']}\n"
        info_text += f"📊 **الجودة:** {info['quality']}\n"
        info_text += f"💾 **الحجم:** {info['size']}\n"
        if info['height'] and info['width']:
            info_text += f"📐 **الدقة:** {info['width']}×{info['height']}\n"
    else:
        info_text += "⏱️ **المدة:** غير معروفة\n"
        info_text += "📊 **الجودة:** غير معروفة\n"
    
    btns = [[InlineKeyboardButton("📢 قناة النشر", url=BACKUP_CHANNEL_LINK)]]
    
    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(current_vid),
            caption=info_text,
            reply_markup=InlineKeyboardMarkup(btns),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Copy Error: {e}")
        await message.reply_text("⚠️ عذراً، تعذر جلب هذا الفيديو")

# ===== دالة عرض العنصر التالي للفحص =====
async def show_next_for_check(client, message, user_id):
    if user_id not in user_check_state or not user_check_state[user_id]:
        await message.edit_text("✅ **تم الانتهاء من فحص جميع الحلقات!**")
        if user_id in user_check_state:
            del user_check_state[user_id]
        return
    
    v_id, title, ep_num = user_check_state[user_id][0]
    
    btns = [
        [
            InlineKeyboardButton("✅ تأكيد", callback_data=f"verify_confirm_{v_id}_{title}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"verify_delete_{v_id}_{title}")
        ],
        [InlineKeyboardButton("❌ إلغاء الفحص", callback_data="cancel_check")]
    ]
    
    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=f"🔍 **فحص الحلقة**\n\n📺 {title} - حلقة {ep_num}\n\n✅ تأكيد = الحلقة سليمة\n🗑️ حذف = إزالة من قاعدة البيانات",
            reply_markup=InlineKeyboardMarkup(btns),
            parse_mode=ParseMode.MARKDOWN
        )
        await message.delete()
    except Exception as e:
        logging.error(f"Error in show_next_for_check: {e}")
        await message.edit_text(
            f"❌ **فشل في إرسال الفيديو**\n\n📺 {title} - حلقة {ep_num}\nID: {v_id}\n\nالخطأ: {str(e)[:200]}\n\n🔄 هل تريد المتابعة؟",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ متابعة", callback_data="next_check")
            ]])
        )

# ===== معالج الضغط على الأزرار =====
@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if data == "next_check":
            if user_id in user_check_state and user_check_state[user_id]:
                user_check_state[user_id] = user_check_state[user_id][1:]
                await callback_query.message.delete()
                await show_next_for_check(client, callback_query.message, user_id)
            await callback_query.answer()
            return
        
        if data == "start_check":
            if user_id != ADMIN_ID:
                await callback_query.answer("❌ هذا الأمر للمدير فقط", show_alert=True)
                return
            
            if user_id not in user_check_state or not user_check_state[user_id]:
                await callback_query.message.edit_text("✅ **لا توجد حلقات للفحص**")
                await callback_query.answer()
                return
            
            await callback_query.message.delete()
            await show_next_for_check(client, callback_query.message, user_id)
            await callback_query.answer()
        
        elif data.startswith("verify_"):
            parts = data.split("_")
            action = parts[1]
            v_id = parts[2]
            series_name = "_".join(parts[3:])
            
            if user_id != ADMIN_ID:
                await callback_query.answer("❌ هذا الأمر للمدير فقط", show_alert=True)
                return
            
            if action == "confirm":
                await callback_query.answer("✅ تم تأكيد صحة هذه الحلقة", show_alert=True)
            
            elif action == "delete":
                db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
                await callback_query.answer("🗑️ تم حذف الحلقة من قاعدة البيانات", show_alert=True)
            
            if user_id in user_check_state:
                user_check_state[user_id] = [item for item in user_check_state[user_id] if item[0] != v_id]
                
                if not user_check_state[user_id]:
                    await callback_query.message.edit_text("✅ **تم الانتهاء من فحص جميع الحلقات!**")
                    del user_check_state[user_id]
                else:
                    await callback_query.message.delete()
                    await show_next_for_check(client, callback_query.message, user_id)
        
        elif data == "cancel_check":
            if user_id in user_check_state:
                del user_check_state[user_id]
            await callback_query.message.edit_text("✅ **تم إلغاء الفحص**")
            await callback_query.answer()
    
    except Exception as e:
        logging.error(f"Error in callback: {e}")
        await callback_query.answer("حدث خطأ", show_alert=True)

# ===== أمر الإحصائيات المتقدمة (بدون تشفير للمدير) =====
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    """إحصائيات متقدمة - تظهر الأسماء كاملة للمدير"""
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط.")
    
    status_msg = await message.reply_text("📊 جاري تحليل الإحصائيات...")
    
    # إحصائيات عامة
    total_videos = db_query("SELECT COUNT(*) FROM videos")[0][0]
    total_views = db_query("SELECT SUM(views) FROM videos")[0][0] or 0
    unique_series = db_query("SELECT COUNT(DISTINCT title) FROM videos WHERE title IS NOT NULL")[0][0]
    
    # إحصائيات اليوم
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_views = db_query("SELECT COUNT(*) FROM videos WHERE last_view >= %s", (today_start,))[0][0]
    
    # إحصائيات الأمس
    yesterday_start = today_start - timedelta(days=1)
    yesterday_end = today_start
    yesterday_views = db_query("SELECT COUNT(*) FROM videos WHERE last_view >= %s AND last_view < %s", 
                              (yesterday_start, yesterday_end))[0][0]
    
    # إحصائيات هذا الأسبوع
    week_start = today_start - timedelta(days=7)
    week_views = db_query("SELECT COUNT(*) FROM videos WHERE last_view >= %s", (week_start,))[0][0]
    
    # أكثر 5 مسلسلات مشاهدة (بدون تشفير للمدير)
    top_series = db_query("""
        SELECT title, SUM(views) as total_views 
        FROM videos 
        WHERE title IS NOT NULL 
        GROUP BY title 
        ORDER BY total_views DESC 
        LIMIT 5
    """)
    
    # أكثر 5 حلقات مشاهدة (بدون تشفير)
    top_episodes = db_query("""
        SELECT title, ep_num, views 
        FROM videos 
        WHERE status = 'posted' AND ep_num > 0 
        ORDER BY views DESC 
        LIMIT 5
    """)
    
    # آخر 5 مشاهدات (بدون تشفير)
    recent_views = db_query("""
        SELECT title, ep_num, last_view 
        FROM videos 
        WHERE last_view IS NOT NULL 
        ORDER BY last_view DESC 
        LIMIT 5
    """)
    
    # بناء التقرير - الأسماء كاملة للمدير
    text = "📊 **إحصائيات متقدمة**\n\n"
    
    text += "**📌 إحصائيات عامة:**\n"
    text += f"• عدد المسلسلات: {unique_series}\n"
    text += f"• عدد الحلقات: {total_videos}\n"
    text += f"• إجمالي المشاهدات: {total_views:,}\n\n"
    
    text += "**📈 المشاهدات:**\n"
    text += f"• اليوم: {today_views}\n"
    text += f"• الأمس: {yesterday_views}\n"
    text += f"• آخر 7 أيام: {week_views}\n\n"
    
    if top_series:
        text += "**🏆 أكثر 5 مسلسلات مشاهدة:**\n"
        for i, (title, views) in enumerate(top_series, 1):
            text += f"{i}. {title} - {views} مشاهدة\n"
        text += "\n"
    
    if top_episodes:
        text += "**⭐ أكثر 5 حلقات مشاهدة:**\n"
        for title, ep, views in top_episodes:
            text += f"• {title} (حلقة {ep}) - {views} مشاهدة\n"
        text += "\n"
    
    if recent_views:
        text += "**🕐 آخر المشاهدات:**\n"
        for title, ep, last_view in recent_views:
            if last_view:
                time_str = last_view.strftime("%Y-%m-%d %H:%M")
                text += f"• {title} (حلقة {ep}) - {time_str}\n"
    
    await status_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("check") & filters.private)
async def check_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔍 جاري تحليل قاعدة البيانات...")
    
    series_list = db_query("SELECT DISTINCT title FROM videos WHERE status = 'posted' AND title IS NOT NULL")
    
    all_issues = []
    
    for (title,) in series_list:
        episodes = db_query("""
            SELECT v_id, ep_num FROM videos 
            WHERE title = %s AND status = 'posted' 
            ORDER BY ep_num ASC, CAST(v_id AS INTEGER) DESC
        """, (title,))
        
        ep_dict = {}
        for v_id, ep_num in episodes:
            if ep_num not in ep_dict:
                ep_dict[ep_num] = []
            ep_dict[ep_num].append((v_id, ep_num))
        
        for ep_num, entries in ep_dict.items():
            if len(entries) > 1:
                for v_id, _ in entries[1:]:
                    all_issues.append((v_id, title, ep_num))
            else:
                v_id, _ = entries[0]
                if not await is_valid_video(client, v_id):
                    all_issues.append((v_id, title, ep_num))
    
    if not all_issues:
        await status_msg.edit_text("✅ **لا توجد حلقات مكررة أو معطلة!**\n\nقاعدة البيانات نظيفة تماماً.")
        return
    
    user_check_state[message.from_user.id] = all_issues
    
    await status_msg.edit_text(
        f"🔍 **تم العثور على {len(all_issues)} حلقة تحتاج للفحص**\n\n"
        f"سيتم عرض كل حلقة واحدة تلو الأخرى.\n"
        f"✅ = الحلقة سليمة (اتركها)\n"
        f"🗑️ = الحلقة معطلة/مكررة (احذفها)",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ بدء الفحص", callback_data="start_check")
        ]])
    )

@app.on_message(filters.command("fix") & filters.private)
async def fix_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔍 جاري البحث عن الإدخالات غير الصالحة...")
    
    all_entries = db_query("SELECT v_id, title, ep_num FROM videos WHERE status = 'posted'")
    deleted = 0
    invalid_list = []
    
    for v_id, title, ep_num in all_entries:
        if not await is_valid_video(client, v_id):
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            deleted += 1
            if len(invalid_list) < 10:
                invalid_list.append(f"• {title} - حلقة {ep_num}")
    
    if deleted > 0:
        report = f"✅ **تم الحذف!**\n"
        report += f"تمت إزالة {deleted} إدخال غير صالح.\n\n"
        if invalid_list:
            report += "**المحذوفات:**\n" + "\n".join(invalid_list)
            if deleted > 10:
                report += f"\n... و{deleted - 10} إدخالات أخرى"
    else:
        report = f"✅ **لا توجد إدخالات غير صالحة!**"
    
    await status_msg.edit_text(report)

@app.on_message(filters.command("id") & filters.private)
async def id_command(client, message):
    await message.reply_text(f"معرفك: `{message.from_user.id}`")

# ===== معالج قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        logging.info(f"📥 رسالة جديدة - ID: {message.id}, Type: {message.media}")
        
        if message.video or message.document:
            video_id = str(message.id)
            db_query("DELETE FROM videos WHERE v_id = %s", (video_id,), fetch=False)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting')", (video_id,), fetch=False)
            await message.reply_text(
                "✅ **تم استلام الفيديو!**\n"
                "📌 أرسل الآن **البوستر** مع اسم المسلسل.\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🎬 Video ID: `{video_id}`"
            )
        
        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await message.reply_text("❌ لا يوجد فيديو في الانتظار. أرسل الفيديو أولاً.")
                return
            
            video_id = res[0][0]
            title = message.caption or "مسلسل"
            
            db_query(
                "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s",
                (title, message.photo.file_id, video_id),
                fetch=False
            )
            
            await message.reply_text(
                f"📌 **تم حفظ البوستر** لـ: {title}\n"
                f"🔢 أرسل الآن **رقم الحلقة** فقط:\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🎬 Video ID: `{video_id}`"
            )
        
        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await message.reply_text("❌ لا يوجد فيديو في انتظار رقم الحلقة.")
                return
            
            video_id, title, poster_id = res[0]
            ep_num = int(message.text)
            
            db_query("DELETE FROM videos WHERE title = %s AND ep_num = %s AND v_id != %s", 
                    (title, ep_num, video_id), fetch=False)
            
            db_query(
                "UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s",
                (ep_num, video_id),
                fetch=False
            )
            
            username = (await app.get_me()).username
            encrypted_title = encrypt_title(title, level=2)
            pub_caption = f"🎬 <b>{encrypted_title}</b>\n\n<b>الحلقة: [{ep_num}]</b>"
            pub_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ مشاهدة", url=f"https://t.me/{username}?start={video_id}")
            ]])
            
            await client.send_photo(
                chat_id=PUBLIC_POST_CHANNEL,
                photo=poster_id,
                caption=pub_caption,
                reply_markup=pub_markup
            )
            
            await message.reply_text(
                f"✅ **تم النشر بنجاح!**\n"
                f"🎬 {title} - حلقة {ep_num}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📺 Video ID: `{video_id}`"
            )
    
    except Exception as e:
        logging.error(f"خطأ في معالج المصدر: {e}")
        await message.reply_text(f"❌ حدث خطأ: {str(e)[:100]}")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    init_database()
    logging.info("🚀 بدء التشغيل...")
    app.run()
