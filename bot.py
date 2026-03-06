import os
import psycopg2
import re
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"  # رابط القناة الاحتياطية
ADMIN_ID = 7720165591

app = Client("railway_final_stable", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ذاكرة مؤقتة
BOT_CACHE = {"username": None}

# ===== دوال قاعدة البيانات =====
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
    """إنشاء جدول قاعدة البيانات إذا لم يكن موجوداً"""
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
    """تشفير أسماء المسلسلات للعرض"""
    if not title:
        return "مسلسل"
    if len(title) <= 6:
        return title
    return title[:3] + "..." + title[-3:]

async def get_bot_username():
    if not BOT_CACHE["username"]:
        me = await app.get_me()
        BOT_CACHE["username"] = me.username
    return BOT_CACHE["username"]

# ===== معالج الأوامر في الخاص =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        if len(message.command) > 1:
            v_id = message.command[1]
            
            # التحقق من وجود الحلقة
            video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
            if not video_info:
                return await message.reply_text("⚠️ الحلقة غير موجودة.")
            
            title, ep = video_info[0]
            
            # تحديث المشاهدات
            db_query("UPDATE videos SET views = COALESCE(views, 0) + 1, last_view = CURRENT_TIMESTAMP WHERE v_id = %s", (v_id,), fetch=False)
            
            # جلب جميع حلقات نفس المسلسل
            episodes = db_query("""
                SELECT v_id, ep_num 
                FROM videos 
                WHERE title = %s AND status = 'posted' AND ep_num IS NOT NULL 
                ORDER BY ep_num ASC
            """, (title,))
            
            # بناء أزرار الحلقات
            username = await get_bot_username()
            btns = []
            row = []
            
            for vid, ep_num in episodes:
                # تمييز الحلقة الحالية
                if str(vid) == str(v_id):
                    label = f"✅ {ep_num}"
                else:
                    label = str(ep_num)
                
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
            btns.append([InlineKeyboardButton("📢 القناة", url=BACKUP_CHANNEL_LINK)])
            
            # إرسال الفيديو
            try:
                await client.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=SOURCE_CHANNEL,
                    message_id=int(v_id),
                    caption=f"<b>📺 {encrypt_title(title)} - حلقة {ep}</b>",
                    reply_markup=InlineKeyboardMarkup(btns),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logging.error(f"خطأ في نسخ الفيديو: {e}")
                await message.reply_text("⚠️ حدث خطأ في جلب الفيديو.")
        
        else:
            # رسالة الترحيب
            welcome_btns = [[InlineKeyboardButton("📢 القناة", url=BACKUP_CHANNEL_LINK)]]
            await message.reply_text(
                "👋 أهلاً بك في بوت المسلسلات!\n"
                "تابع قناتنا لمشاهدة أحدث الحلقات.",
                reply_markup=InlineKeyboardMarkup(welcome_btns)
            )
    
    except Exception as e:
        logging.error(f"خطأ في start: {e}")
        await message.reply_text("❌ حدث خطأ، حاول مرة أخرى.")

@app.on_message(filters.command("id") & filters.private)
async def id_command(client, message):
    await message.reply_text(f"معرفك: `{message.from_user.id}`")

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    try:
        if message.from_user.id != ADMIN_ID:
            return await message.reply_text("❌ هذا الأمر للمدير فقط.")
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # إحصائيات عامة
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
        
        # أشهر 5 مسلسلات كل الوقت
        top_series = db_query("""
            SELECT title, SUM(views) as total_views 
            FROM videos 
            WHERE title IS NOT NULL 
            GROUP BY title 
            ORDER BY total_views DESC 
            LIMIT 5
        """)
        
        # آخر 5 حلقات
        recent_eps = db_query("""
            SELECT title, ep_num, views 
            FROM videos 
            WHERE status = 'posted' AND ep_num IS NOT NULL
            ORDER BY CAST(v_id AS INTEGER) DESC 
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
        
        if recent_eps:
            text += f"\n**🆕 آخر الحلقات:**\n"
            for title, ep, views in recent_eps:
                text += f"• {encrypt_title(title)} (حلقة {ep}) - {views} مشاهدة\n"
        
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("debug") & filters.private)
async def debug_command(client, message):
    try:
        if message.from_user.id != ADMIN_ID:
            return await message.reply_text("❌ هذا الأمر للمدير فقط.")
        
        text = "🔍 **تشخيص البوت**\n\n"
        
        me = await client.get_me()
        text += f"**معلومات البوت:**\n"
        text += f"• الاسم: {me.first_name}\n"
        text += f"• اليوزرنيم: @{me.username}\n"
        text += f"• المعرف: {me.id}\n\n"
        
        # قناة المصدر
        try:
            channel = await client.get_chat(SOURCE_CHANNEL)
            text += f"**قناة المصدر:**\n"
            text += f"• الاسم: {channel.title}\n"
            text += f"• المعرف: {channel.id}\n"
            bot_member = await client.get_chat_member(SOURCE_CHANNEL, "me")
            text += f"• صلاحية البوت: {bot_member.status}\n\n"
        except Exception as e:
            text += f"• ❌ خطأ في قناة المصدر: {e}\n\n"
        
        # قاعدة البيانات
        count = db_query("SELECT COUNT(*) FROM videos")[0][0]
        text += f"**قاعدة البيانات:**\n"
        text += f"• عدد الفيديوهات: {count}\n"
        
        recent = db_query("SELECT v_id, title, ep_num, status, views FROM videos ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 5")
        if recent:
            text += f"\n**آخر 5 فيديوهات:**\n"
            for v_id, title, ep, status, views in recent:
                text += f"• {v_id}: {encrypt_title(title) if title else 'بدون عنوان'} | حلقة {ep or '?'} | {status} | {views} مشاهدة\n"
        
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== معالج قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        logging.info(f"📥 رسالة جديدة - ID: {message.id}, Type: {message.media}")
        
        # فيديو
        if message.video or message.document:
            v_id = str(message.id)
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting')", (v_id,), fetch=False)
            
            await client.send_message(
                SOURCE_CHANNEL,
                "✅ تم استلام الفيديو!\n📌 أرسل الآن البوستر (صورة) مع اسم المسلسل في الوصف:",
                reply_to_message_id=message.id
            )
        
        # بوستر
        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await client.send_message(
                    SOURCE_CHANNEL,
                    "❌ لا يوجد فيديو في الانتظار. أرسل الفيديو أولاً.",
                    reply_to_message_id=message.id
                )
                return
            
            v_id = res[0][0]
            title = message.caption or "مسلسل"
            
            db_query(
                "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s",
                (title, message.photo.file_id, v_id),
                fetch=False
            )
            
            await client.send_message(
                SOURCE_CHANNEL,
                f"📌 تم حفظ البوستر لـ: {title}\n🔢 أرسل الآن رقم الحلقة فقط:",
                reply_to_message_id=message.id
            )
        
        # رقم الحلقة
        elif message.text and message.text.strip().isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await client.send_message(
                    SOURCE_CHANNEL,
                    "❌ لا يوجد فيديو في انتظار رقم الحلقة.",
                    reply_to_message_id=message.id
                )
                return
            
            v_id, title, p_id = res[0]
            ep_num = int(message.text.strip())
            
            db_query(
                "UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s",
                (ep_num, v_id),
                fetch=False
            )
            
            # النشر في القناة العامة
            username = await get_bot_username()
            pub_caption = f"🎬 <b>{encrypt_title(title)}</b>\n\n<b>الحلقة: [{ep_num}]</b>"
            pub_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{username}?start={v_id}")
            ]])
            
            try:
                await client.send_photo(
                    chat_id=PUBLIC_POST_CHANNEL,
                    photo=p_id,
                    caption=pub_caption,
                    reply_markup=pub_markup,
                    parse_mode=ParseMode.HTML
                )
                
                await client.send_message(
                    SOURCE_CHANNEL,
                    f"✅ تم النشر بنجاح!\n🎬 {title} - حلقة {ep_num}",
                    reply_to_message_id=message.id
                )
            except Exception as e:
                await client.send_message(
                    SOURCE_CHANNEL,
                    f"❌ فشل النشر: {e}",
                    reply_to_message_id=message.id
                )
    
    except Exception as e:
        logging.error(f"خطأ في معالج القناة: {e}")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    init_database()
    logging.info("🚀 بدء تشغيل البوت...")
    app.run()
