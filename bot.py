import os, re, psycopg2, logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType
import asyncio

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = int(-1003547072209)      # قناة المصدر (فيها الفيديوهات)
PUBLIC_POST_CHANNEL = int(-1003554018307)  # قناة النشر (فيها المنشورات)
ADMIN_ID = int(7720165591)
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("railway_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دالة قاعدة البيانات =====
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
        logger.error(f"DB Error: {e}")
        return []

# ===== [3] استقبال الفيديوهات من قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source_video(client, message):
    """عند إضافة فيديو في قناة المصدر"""
    try:
        if message.video or message.document:
            # تخزين معلومات الفيديو
            title = message.caption.strip() if message.caption else "غير مسمى"
            db_query("""
                INSERT INTO videos (v_id, title, status) 
                VALUES (%s, %s, 'waiting_poster') 
                ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title
            """, (str(message.id), title), fetch=False)
            logger.info(f"تم استقبال فيديو جديد: {message.id}")
        
        elif message.photo:
            # ربط البوستر بآخر فيديو
            res = db_query("""
                SELECT v_id FROM videos 
                WHERE status = 'waiting_poster' 
                ORDER BY v_id DESC LIMIT 1
            """)
            if res:
                db_query("""
                    UPDATE videos 
                    SET poster_id = %s, status = 'waiting_ep' 
                    WHERE v_id = %s
                """, (message.photo.file_id, res[0][0]), fetch=False)
                logger.info(f"تم ربط البوستر بالفيديو {res[0][0]}")
        
        elif message.text and message.text.isdigit():
            # ربط رقم الحلقة بآخر فيديو
            res = db_query("""
                SELECT v_id, title, poster_id FROM videos 
                WHERE status = 'waiting_ep' 
                ORDER BY v_id DESC LIMIT 1
            """)
            if res:
                v_id, title, poster_id = res[0]
                ep_num = int(message.text)
                
                # تحديث قاعدة البيانات
                db_query("""
                    UPDATE videos 
                    SET ep_num = %s, status = 'posted' 
                    WHERE v_id = %s
                """, (ep_num, v_id), fetch=False)
                
                # إنشاء رابط البوت
                me = await client.get_me()
                bot_link = f"https://t.me/{me.username}?start={v_id}"
                
                # إرسال المنشور إلى القناة العامة
                caption = f"🎬 <b>{title}</b>\n📌 <b>الحلقة: {ep_num}</b>\n\n👇 اضغط على الزر للمشاهدة"
                
                await client.send_photo(
                    PUBLIC_POST_CHANNEL,
                    poster_id,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎥 مشاهدة الحلقة", url=bot_link)
                    ]])
                )
                
                logger.info(f"تم نشر الحلقة {ep_num} من {title}")
                
    except Exception as e:
        logger.error(f"خطأ في معالجة المصدر: {e}")

# ===== [4] عرض الحلقة للمستخدم =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    """عندما يضغط المستخدم على رابط المشاهدة"""
    try:
        # استخراج معرف الفيديو من الرابط
        if len(message.command) > 1:
            v_id = message.command[1]
            
            # جلب معلومات الفيديو من قاعدة البيانات
            res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
            
            if res:
                title, ep_num = res[0]
                
                # جلب جميع حلقات نفس المسلسل
                all_eps = db_query("""
                    SELECT ep_num, v_id FROM videos 
                    WHERE title = %s AND status = 'posted' 
                    ORDER BY ep_num ASC
                """, (title,))
                
                # بناء أزرار التنقل
                buttons = []
                row = []
                for e_num, e_vid in all_eps:
                    # تمييز الحلقة الحالية
                    btn_text = f"● {e_num} ●" if str(e_vid) == v_id else str(e_num)
                    row.append(InlineKeyboardButton(btn_text, callback_data=f"ep_{e_vid}"))
                    
                    if len(row) == 5:
                        buttons.append(row)
                        row = []
                
                if row:
                    buttons.append(row)
                
                # إضافة زر قناة الاحتياط
                buttons.append([InlineKeyboardButton("📢 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])
                
                # إرسال الفيديو للمستخدم
                caption = f"📺 <b>{title}</b>\n🎬 <b>الحلقة {ep_num}</b>"
                
                await client.copy_message(
                    message.chat.id,
                    SOURCE_CHANNEL,
                    int(v_id),
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            else:
                await message.reply_text("❌ هذه الحلقة غير موجودة في قاعدة البيانات")
        else:
            # رسالة الترحيب
            welcome_text = """
👋 مرحباً بك في بوت المسلسلات

للمشاهدة، انقر على زر "مشاهدة" في منشورات القناة
أو استخدم الروابط المباشرة من القناة

📢 قناة الاحتياط: https://t.me/+7AC_HNR8QFI5OWY0
            """
            await message.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📢 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)
                ]])
            )
            
    except Exception as e:
        logger.error(f"خطأ في عرض الحلقة: {e}")
        await message.reply_text("❌ حدث خطأ، الرجاء المحاولة لاحقاً")

# ===== [5] معالجة أزرار التنقل =====
@app.on_callback_query(filters.regex(r"^ep_"))
async def episode_navigation(client, callback):
    """عند الضغط على أزرار التنقل بين الحلقات"""
    try:
        v_id = callback.data.split("_")[1]
        
        # جلب معلومات الفيديو
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if res:
            title, ep_num = res[0]
            
            # حذف الرسالة القديمة
            await callback.message.delete()
            
            # إرسال الحلقة الجديدة
            caption = f"📺 <b>{title}</b>\n🎬 <b>الحلقة {ep_num}</b>"
            
            sent_msg = await client.copy_message(
                callback.message.chat.id,
                SOURCE_CHANNEL,
                int(v_id),
                caption=caption
            )
            
            # إعادة إضافة أزرار التنقل
            all_eps = db_query("""
                SELECT ep_num, v_id FROM videos 
                WHERE title = %s AND status = 'posted' 
                ORDER BY ep_num ASC
            """, (title,))
            
            buttons = []
            row = []
            for e_num, e_vid in all_eps:
                btn_text = f"● {e_num} ●" if str(e_vid) == v_id else str(e_num)
                row.append(InlineKeyboardButton(btn_text, callback_data=f"ep_{e_vid}"))
                
                if len(row) == 5:
                    buttons.append(row)
                    row = []
            
            if row:
                buttons.append(row)
            
            buttons.append([InlineKeyboardButton("📢 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])
            
            await sent_msg.edit_reply_markup(InlineKeyboardMarkup(buttons))
            
        await callback.answer()
        
    except Exception as e:
        logger.error(f"خطأ في التنقل: {e}")
        await callback.answer("❌ حدث خطأ", show_alert=True)

# ===== [6] أوامر التحكم للمشرف =====
@app.on_message(filters.command("test") & filters.private)
async def test_command(client, message):
    """اختبار اتصال البوت بالقنوات"""
    if message.from_user.id != ADMIN_ID:
        await message.reply_text("❌ هذا الأمر للمشرف فقط")
        return
    
    try:
        result = "🔍 **نتائج الفحص:**\n\n"
        
        # فحص قناة المصدر
        try:
            source_chat = await client.get_chat(SOURCE_CHANNEL)
            result += f"✅ قناة المصدر: {source_chat.title}\n"
        except Exception as e:
            result += f"❌ قناة المصدر: خطأ - {str(e)}\n"
        
        # فحص قناة النشر
        try:
            post_chat = await client.get_chat(PUBLIC_POST_CHANNEL)
            result += f"✅ قناة النشر: {post_chat.title}\n"
        except Exception as e:
            result += f"❌ قناة النشر: خطأ - {str(e)}\n"
        
        # إحصائيات قاعدة البيانات
        total = db_query("SELECT COUNT(*) FROM videos")[0][0]
        posted = db_query("SELECT COUNT(*) FROM videos WHERE status = 'posted'")[0][0]
        waiting = db_query("SELECT COUNT(*) FROM videos WHERE status != 'posted'")[0][0]
        
        result += f"\n📊 **إحصائيات:**\n"
        result += f"• إجمالي الحلقات: {total}\n"
        result += f"• منشورة: {posted}\n"
        result += f"• قيد الانتظار: {waiting}\n"
        
        await message.reply_text(result)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ عام: {str(e)}")

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    """عرض إحصائيات قاعدة البيانات"""
    if message.from_user.id != ADMIN_ID:
        await message.reply_text("❌ هذا الأمر للمشرف فقط")
        return
    
    try:
        # إحصائيات عامة
        stats = db_query("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'posted' THEN 1 ELSE 0 END) as posted,
                COUNT(DISTINCT title) as series
            FROM videos
        """)[0]
        
        total, posted, series = stats
        
        # أحدث 5 حلقات
        recent = db_query("""
            SELECT title, ep_num FROM videos 
            WHERE status = 'posted' 
            ORDER BY v_id DESC LIMIT 5
        """)
        
        result = f"📊 **إحصائيات البوت:**\n\n"
        result += f"• عدد المسلسلات: {series}\n"
        result += f"• إجمالي الحلقات: {total}\n"
        result += f"• الحلقات المنشورة: {posted}\n"
        result += f"• الحلقات قيد الانتظار: {total - posted}\n"
        
        if recent:
            result += f"\n🆕 **آخر الحلقات:**\n"
            for title, ep in recent:
                result += f"• {title} - حلقة {ep}\n"
        
        await message.reply_text(result)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {str(e)}")

if __name__ == "__main__":
    # إنشاء جداول قاعدة البيانات
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            poster_id TEXT,
            status TEXT DEFAULT 'waiting_poster'
        )
    """, fetch=False)
    
    # إضافة فهارس لتحسين الأداء
    db_query("CREATE INDEX IF NOT EXISTS idx_status ON videos(status)", fetch=False)
    db_query("CREATE INDEX IF NOT EXISTS idx_title ON videos(title)", fetch=False)
    
    logger.info("🚀 البوت يعمل الآن...")
    app.run()
