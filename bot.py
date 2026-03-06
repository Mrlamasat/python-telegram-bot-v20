import os
import psycopg2
import re
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import PeerIdInvalid, UserNotParticipant

# إعداد السجلات
logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# قناة المصدر (التي ترفع فيها الفيديوهات)
SOURCE_CHANNEL = -1003547072209

# قنوات النشر الخاصة (التي تحتوي على الأرقام الصحيحة)
PUBLISH_CHANNELS = [
    -1003554018307,
    -1003790915936,
    -1003678294148
]

BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== وظائف قاعدة البيانات =====
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
    if not title: return "مسلسل"
    if len(title) <= 6: return title
    return title[:3] + "..." + title[-3:]

async def get_bot_username():
    me = await app.get_me()
    return me.username

async def is_valid_video(client, v_id):
    """التحقق من وجود الفيديو في قناة المصدر"""
    try:
        msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        return msg and not msg.empty
    except:
        return False

# ===== دالة عرض الحلقة (المطورة لمنع التكرار وفحص الفيديو) =====
async def show_episode(client, message, current_vid):
    # 1. جلب معلومات الحلقة المطلوبة
    video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not video_info:
        await message.reply_text("⚠️ هذه الحلقة غير موجودة في قاعدة البيانات.")
        return
    
    title, current_ep = video_info[0]
    clean_title = title.strip()
    
    # تحديث المشاهدات
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    # 2. جلب جميع الحلقات المنشورة لنفس المسلسل
    all_episodes = db_query("""
        SELECT v_id, ep_num FROM videos 
        WHERE TRIM(title) = %s AND status = 'posted' AND ep_num > 0 
        ORDER BY ep_num ASC
    """, (clean_title,))
    
    # 3. تصفية الحلقات: التأكد من وجود الفيديو ومنع تكرار الرقم
    btns, row = [], []
    seen_episodes = set()  # مخزن للأرقام التي تم عرضها بالفعل
    valid_count = 0
    
    for vid, ep_num in all_episodes:
        # أ: منع تكرار نفس رقم الحلقة في الواجهة
        if ep_num in seen_episodes:
            continue
            
        # ب: فحص حي: هل الفيديو موجود فعلاً في قناة المصدر؟
        try:
            # نحاول جلب الرسالة من قناة المصدر، إذا فشل سينتقل للـ except
            check_msg = await client.get_messages(SOURCE_CHANNEL, int(vid))
            if not check_msg or check_msg.empty:  # إذا كانت الرسالة محذوفة
                continue
        except Exception:
            # إذا حدث خطأ (القناة غير موجودة أو الرسالة محذوفة) يتخطى الحلقة
            continue
            
        # ج: إذا اجتاز الفحص، نضيف الرقم للمجموعة ونبني الزر
        seen_episodes.add(ep_num)
        valid_count += 1
        
        # تمييز الحلقة الحالية
        label = f"✅ {ep_num}" if str(vid) == str(current_vid) else str(ep_num)
        
        # استخدام URL بدلاً من callback_data
        username = await get_bot_username()
        row.append(InlineKeyboardButton(
            label, 
            url=f"https://t.me/{username}?start={vid}"
        ))
        
        if len(row) == 5:  # 5 أزرار في كل سطر
            btns.append(row)
            row = []
            
    if row:
        btns.append(row)
    
    # إضافة زر القناة في الأسفل
    btns.append([InlineKeyboardButton("📢 قناة النشر الأساسية", url=BACKUP_CHANNEL_LINK)])
    
    # 4. إرسال الفيديو (نسخ)
    if valid_count > 0:
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
            await message.reply_text("⚠️ عذراً، تعذر جلب هذا الفيديو (قد يكون محذوفاً من المصدر).")
    else:
        await message.reply_text("⚠️ لا توجد حلقات صالحة لهذا المسلسل حالياً.")

# ===== معالجات الأوامر (للمستخدم) =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        if len(message.command) > 1:
            v_id = message.command[1]
            
            # التحقق السريع من وجود الفيديو
            if not await is_valid_video(client, v_id):
                return await message.reply_text("⚠️ هذه الحلقة غير متوفرة حالياً في المصدر.")
            
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
        logging.error(f"Start Error: {e}")
        await message.reply_text("حدث خطأ، حاول مرة أخرى")

# ===== أوامر الإدارة (ADMIN) =====
@app.on_message(filters.command("sync") & filters.private)
async def sync_channels(client, message):
    if message.from_user.id != ADMIN_ID: 
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔄 جاري مزامنة الأرقام من قنوات النشر الخاصة...")
    updated = 0
    failed_channels = []
    
    for channel_id in PUBLISH_CHANNELS:
        try:
            # محاولة جلب معلومات القناة للتأكد من وجود البوت فيها
            try:
                await client.get_chat(channel_id)
            except PeerIdInvalid:
                failed_channels.append(f"❌ القناة {channel_id}: معرف غير صالح")
                continue
            except UserNotParticipant:
                failed_channels.append(f"❌ القناة {channel_id}: البوت ليس عضواً")
                continue
            
            channel_updated = 0
            async for msg in client.get_chat_history(channel_id, limit=200):
                if msg.reply_markup and msg.caption and msg.reply_markup.inline_keyboard:
                    try:
                        url = msg.reply_markup.inline_keyboard[0][0].url
                        if "start=" not in url: 
                            continue
                        v_id = url.split("start=")[1]
                        
                        # استخراج الرقم من المنشور
                        match = re.search(r'\[(\d+)\]|حلقة\s*(\d+)|الحلقة\s*(\d+)', msg.caption, re.IGNORECASE)
                        if match:
                            correct_ep = int(match.group(1) or match.group(2) or match.group(3))
                            db_query("UPDATE videos SET ep_num = %s, status = 'posted' WHERE v_id = %s", (correct_ep, v_id), fetch=False)
                            channel_updated += 1
                    except Exception as e:
                        logging.error(f"Error processing message in {channel_id}: {e}")
                        continue
            
            updated += channel_updated
            failed_channels.append(f"✅ القناة {channel_id}: تم تحديث {channel_updated} حلقة")
            
        except Exception as e:
            failed_channels.append(f"⚠️ القناة {channel_id}: {str(e)[:50]}")
            logging.error(f"Sync error in {channel_id}: {e}")

    # إعداد التقرير النهائي
    report = f"✅ **تمت المزامنة!**\n"
    report += f"📊 إجمالي الحلقات المصححة: {updated}\n\n"
    report += "**تفاصيل القنوات:**\n"
    report += "\n".join(failed_channels)
    
    await status_msg.edit_text(report)

@app.on_message(filters.command("fix") & filters.private)
async def fix_database(client, message):
    if message.from_user.id != ADMIN_ID: 
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔍 جاري حذف الإدخالات غير الصالحة...")
    
    all_entries = db_query("SELECT v_id, title, ep_num FROM videos WHERE status = 'posted'")
    deleted = 0
    invalid_list = []
    
    for v_id, title, ep_num in all_entries:
        if not await is_valid_video(client, v_id):
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            deleted += 1
            if len(invalid_list) < 10:  # نحتفظ بأول 10 فقط للتقرير
                invalid_list.append(f"• {encrypt_title(title)} - حلقة {ep_num}")
    
    report = f"✅ **تم التنظيف!**\n"
    report += f"📊 تم حذف {deleted} إدخال ليس له فيديو في المصدر.\n\n"
    
    if invalid_list:
        report += "**المحذوفات:**\n" + "\n".join(invalid_list)
        if deleted > 10:
            report += f"\n... و{deleted - 10} إدخالات أخرى"
    
    await status_msg.edit_text(report)

@app.on_message(filters.command("channels") & filters.private)
async def check_channels(client, message):
    """أمر للتحقق من حالة القنوات"""
    if message.from_user.id != ADMIN_ID: 
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    status_msg = await message.reply_text("🔍 جاري التحقق من القنوات...")
    
    result = []
    for channel_id in PUBLISH_CHANNELS:
        try:
            chat = await client.get_chat(channel_id)
            result.append(f"✅ {chat.title}\n   • المعرف: `{channel_id}`\n   • النوع: {chat.type}")
        except PeerIdInvalid:
            result.append(f"❌ معرف غير صالح: `{channel_id}`")
        except UserNotParticipant:
            result.append(f"⚠️ البوت ليس عضواً: `{channel_id}`")
        except Exception as e:
            result.append(f"⚠️ خطأ: `{channel_id}` - {str(e)[:50]}")
    
    report = "**📊 حالة القنوات:**\n\n" + "\n\n".join(result)
    await status_msg.edit_text(report)

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: 
        return await message.reply_text("❌ هذا الأمر للمدير فقط")
    
    # إحصائيات متنوعة
    total = db_query("SELECT COUNT(*) FROM videos")[0][0]
    posted = db_query("SELECT COUNT(*) FROM videos WHERE status='posted'")[0][0]
    waiting = db_query("SELECT COUNT(*) FROM videos WHERE status='waiting'")[0][0]
    awaiting_ep = db_query("SELECT COUNT(*) FROM videos WHERE status='awaiting_ep'")[0][0]
    total_views = db_query("SELECT SUM(views) FROM videos")[0][0] or 0
    unique_series = db_query("SELECT COUNT(DISTINCT title) FROM videos WHERE title IS NOT NULL")[0][0]
    
    report = f"📊 **إحصائيات البوت**\n\n"
    report += f"**المسلسلات:** {unique_series}\n"
    report += f"**إجمالي الحلقات:** {total}\n"
    report += f"• منشورة: {posted}\n"
    report += f"• في الانتظار: {waiting}\n"
    report += f"• تنتظر رقم: {awaiting_ep}\n"
    report += f"**إجمالي المشاهدات:** {total_views:,}\n"
    
    await message.reply_text(report)

@app.on_message(filters.command("id") & filters.private)
async def id_command(client, message):
    await message.reply_text(f"معرفك: `{message.from_user.id}`")

# ===== معالج قناة المصدر (الرفع) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        if message.video or message.document:
            v_id = str(message.id)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id,), fetch=False)
            await message.reply_text("✅ تم استلام الفيديو!\nأرسل البوستر مع اسم المسلسل:")
        
        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id = res[0][0]
                title = message.caption or "مسلسل"
                db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
                await message.reply_text(f"📌 تم حفظ البوستر لـ: {title}\nأرسل الآن رقم الحلقة فقط:")
            else:
                await message.reply_text("❌ لا يوجد فيديو في الانتظار. أرسل الفيديو أولاً.")
        
        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id, title, p_id = res[0]
                ep_num = int(message.text)
                db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
                
                # النشر في أول قناة نشر متاحة
                username = await get_bot_username()
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=f"https://t.me/{username}?start={v_id}")]])
                
                # محاولة النشر في أول قناة
                try:
                    await client.send_photo(
                        PUBLISH_CHANNELS[0], 
                        p_id, 
                        caption=f"🎬 <b>{encrypt_title(title)}</b>\n\n<b>الحلقة: [{ep_num}]</b>", 
                        reply_markup=markup,
                        parse_mode=ParseMode.HTML
                    )
                    await message.reply_text(f"✅ تم النشر بنجاح: {title} - حلقة {ep_num}")
                except Exception as e:
                    await message.reply_text(f"⚠️ تم الحفظ ولكن فشل النشر: {e}")
            else:
                await message.reply_text("❌ لا يوجد فيديو في انتظار رقم الحلقة.")
    
    except Exception as e:
        logging.error(f"Source Error: {e}")
        await message.reply_text(f"❌ حدث خطأ: {str(e)[:100]}")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    init_database()
    logging.info("🚀 بدء التشغيل...")
    app.run()
