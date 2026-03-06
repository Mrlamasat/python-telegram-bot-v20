import os
import psycopg2
import logging
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

# إعداد السجلات (Logs)
logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية (تأكد من صحتها في ريلوي) =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# المعرفات الخاصة بك يا محمد
SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_stable", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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
    logging.info("✅ قاعدة البيانات جاهزة للعمل")

# ===== دوال مساعدة =====
def encrypt_title(title):
    if not title: return "مسلسل"
    if len(title) <= 6: return title
    return title[:3] + "..." + title[-3:]

async def get_bot_username():
    me = await app.get_me()
    return me.username

# ===== دالة عرض الحلقة (المطورة: فحص حي + منع تكرار) =====
async def show_episode(client, message, current_vid):
    # 1. جلب معلومات الحلقة المطلوبة
    video_info = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (current_vid,))
    if not video_info:
        return await message.reply_text("⚠️ هذه الحلقة غير موجودة في قاعدة البيانات.")
    
    title, current_ep = video_info[0]
    clean_title = title.strip()
    
    # تحديث إحصائيات المشاهدة
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (current_vid,), fetch=False)
    
    # 2. جلب جميع الحلقات المنشورة لهذا المسلسل
    episodes = db_query("""
        SELECT v_id, ep_num FROM videos 
        WHERE TRIM(title) = %s AND status = 'posted' AND ep_num > 0 
        ORDER BY ep_num ASC
    """, (clean_title,))
    
    # 3. بناء الأزرار مع الفحص الحي ومنع التكرار
    btns, row = [], []
    seen_episodes = set() # لضمان عدم تكرار الأرقام في الواجهة
    
    for vid, ep_num in episodes:
        # أ: تخطي إذا كان الرقم ظهر مسبقاً في القائمة
        if ep_num in seen_episodes:
            continue
            
        # ب: الفحص الحي (تأكد أن الفيديو لا يزال في قناة المصدر)
        try:
            check_msg = await client.get_messages(SOURCE_CHANNEL, int(vid))
            if check_msg.empty: # إذا كانت الرسالة محذوفة من القناة
                continue
        except Exception:
            continue # تخطي إذا حدث خطأ في الوصول للقناة
            
        seen_episodes.add(ep_num)
        
        # تلوين الحلقة الحالية بعلامة الصح
        label = f"✅ {ep_num}" if str(vid) == str(current_vid) else str(ep_num)
        
        # استخدام callback_data للتنقل السريع داخل البوت
        row.append(InlineKeyboardButton(label, callback_data=f"ep_{vid}"))
        
        if len(row) == 5: # 5 أزرار في كل صف
            btns.append(row)
            row = []
            
    if row: btns.append(row)
    
    # إضافة زر قناة النشر في الأسفل
    btns.append([InlineKeyboardButton("📢 قناة النشر الأساسية", url=BACKUP_CHANNEL_LINK)])
    
    # 4. إرسال الفيديو (copy_message) مع الأزرار النظيفة
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
        logging.error(f"Copy Message Error: {e}")
        await message.reply_text("⚠️ عذراً، تعذر عرض الفيديو (تأكد أنه لم يتم حذفه من المصدر).")

# ===== معالج الضغط على الأزرار =====
@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    try:
        data = callback_query.data
        if data.startswith("ep_"):
            v_id = data.replace("ep_", "")
            
            # حذف الرسالة القديمة لتجنب تراكم الرسائل
            await callback_query.message.delete()
            
            # عرض الحلقة الجديدة
            await show_episode(client, callback_query.message, v_id)
            await callback_query.answer()
            
    except Exception as e:
        logging.error(f"Callback Error: {e}")
        await callback_query.answer("⚠️ حدث خطأ أثناء التبديل بين الحلقات", show_alert=True)

# ===== معالج أمر Start (للدخول من القناة) =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        if len(message.command) > 1:
            v_id = message.command[1]
            await show_episode(client, message, v_id)
        else:
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("📢 قناة النشر", url=BACKUP_CHANNEL_LINK)]])
            await message.reply_text(f"👋 أهلاً بك يا محمد!\nيرجى اختيار الحلقة من قناة النشر للمشاهدة.", reply_markup=markup)
    except Exception as e:
        logging.error(f"Start command error: {e}")

# ===== معالج قناة المصدر (الرفع التلقائي) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        # حالة 1: استلام الفيديو
        if message.video or message.document:
            v_id = str(message.id)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id,), fetch=False)
            await message.reply_text("✅ تم استلام الفيديو!\n📌 أرسل الآن البوستر مع اسم المسلسل في الوصف:")
        
        # حالة 2: استلام البوستر
        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id = res[0][0]
                db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption or "مسلسل", message.photo.file_id, v_id), fetch=False)
                await message.reply_text(f"📌 تم حفظ البوستر لـ: {message.caption}\n🔢 أرسل الآن رقم الحلقة فقط:")
        
        # حالة 3: استلام رقم الحلقة والنشر
        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if res:
                v_id, title, p_id = res[0]
                ep_num = int(message.text)
                
                # تحديث البيانات النهائية
                db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
                
                # النشر في قناة النشر العامة
                username = await get_bot_username()
                pub_caption = f"🎬 <b>{encrypt_title(title)}</b>\n\n<b>الحلقة: [{ep_num}]</b>"
                pub_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة", url=f"https://t.me/{username}?start={v_id}")]])
                
                await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=pub_caption, reply_markup=pub_markup)
                await message.reply_text(f"✅ تم النشر بنجاح: {title} - حلقة {ep_num}")
                
    except Exception as e:
        logging.error(f"Source handling error: {e}")

# ===== أوامر المدير (Stats) =====
@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != ADMIN_ID: return
    res = db_query("SELECT COUNT(*), SUM(views) FROM videos WHERE status = 'posted'")[0]
    await message.reply_text(f"📊 إحصائيات البوت يا محمد:\n• عدد الحلقات المنشورة: {res[0]}\n• إجمالي المشاهدات: {res[1] or 0:,}")

# ===== تشغيل البوت =====
if __name__ == "__main__":
    init_database()
    logging.info("🚀 البوت يعمل الآن بنجاح...")
    app.run()
