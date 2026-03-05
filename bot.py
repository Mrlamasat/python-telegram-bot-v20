import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ForceReply
from pyrogram.enums import ParseMode

# ===== الإعدادات الأساسية =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307 
FORCE_SUB_CHANNEL = -1003894735143 
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== تحديث قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch: 
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close(); conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== إضافة جداول جديدة للتحديث =====
def init_database():
    """تهيئة قاعدة البيانات مع الجداول الجديدة"""
    # إضافة عمود source_message_id إذا لم يكن موجوداً
    db_query("""
        DO $$ 
        BEGIN 
            BEGIN
                ALTER TABLE videos ADD COLUMN source_message_id BIGINT;
            EXCEPTION
                WHEN duplicate_column THEN 
                    RAISE NOTICE 'column source_message_id already exists';
            END;
        END $$;
    """, fetch=False)
    
    # إضافة عمود target_message_id لتخزين معرف الرسالة المنشورة
    db_query("""
        DO $$ 
        BEGIN 
            BEGIN
                ALTER TABLE videos ADD COLUMN target_message_id BIGINT;
            EXCEPTION
                WHEN duplicate_column THEN 
                    RAISE NOTICE 'column target_message_id already exists';
            END;
        END $$;
    """, fetch=False)
    
    # إضافة جدول لتتبع الرسائل المنشورة
    db_query("""
        CREATE TABLE IF NOT EXISTS published_messages (
            id SERIAL PRIMARY KEY,
            source_message_id BIGINT,
            target_message_id BIGINT,
            target_channel_id BIGINT,
            series_title TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_message_id, target_channel_id)
        )
    """, fetch=False)
    
    # إضافة جدول لتتبع العلاقات بين الحلقات
    db_query("""
        CREATE TABLE IF NOT EXISTS series_episodes (
            series_title TEXT,
            episode_id BIGINT,
            source_message_id BIGINT,
            PRIMARY KEY (series_title, episode_id)
        )
    """, fetch=False)

# استدعاء تهيئة قاعدة البيانات
init_database()

# ===== الدوال المساعدة =====
def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'^(مسلسل|فيلم|برنامج|عرض)\s+', '', text)
    text = re.sub(r'[أإآ]', 'ا', text).replace('ة', 'ه').replace('ى', 'ي')
    text = re.sub(r'[^a-z0-9ا-ي]', '', text)
    return text

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

def extract_title_from_caption(caption):
    """استخراج عنوان المسلسل من الكابشن"""
    if not caption:
        return None
    # البحث عن النص بين علامات <b> في بداية الكابشن
    match = re.search(r'<b>(.*?)</b>', caption)
    if match:
        return match.group(1).replace(' . ', '')  # إزالة التمويه
    return None

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅ {ep_num}" if v_id == current_v_id else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    return buttons

async def check_subscription(client, user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return False

# ===== دالة تحديث العنوان في جميع القنوات =====
async def update_series_title_in_channels(client, old_title, new_title, source_message_id=None):
    """تحديث عنوان المسلسل في جميع القنوات التي نشر فيها"""
    try:
        # البحث عن جميع الحلقات لهذا المسلسل
        if source_message_id:
            # تحديث محدد لمصدر معين
            episodes = db_query("""
                SELECT v_id, target_message_id 
                FROM videos 
                WHERE source_message_id = %s AND target_message_id IS NOT NULL
            """, (source_message_id,))
        else:
            # تحديث جميع حلقات المسلسل
            episodes = db_query("""
                SELECT v_id, target_message_id 
                FROM videos 
                WHERE title = %s AND target_message_id IS NOT NULL
            """, (old_title,))
        
        if not episodes:
            return False
        
        # تحديث كل حلقة
        for v_id, target_msg_id in episodes:
            try:
                # الحصول على معلومات الحلقة
                ep_info = db_query("""
                    SELECT ep_num, quality, duration 
                    FROM videos 
                    WHERE v_id = %s
                """, (v_id,))
                
                if ep_info:
                    ep_num, quality, duration = ep_info[0]
                    
                    # إنشاء كابشن جديد بالعنوان المحدث
                    new_caption = f"🎬 <b>{obfuscate_visual(escape(new_title))}</b>\n\n"
                    new_caption += f"<b>الحلقة: [{ep_num}]</b>\n"
                    new_caption += f"<b>الجودة: [{quality}]</b>\n"
                    new_caption += f"<b>المدة: [{duration}]</b>"
                    
                    # تحديث الرسالة في القناة
                    await client.edit_message_caption(
                        chat_id=PUBLIC_POST_CHANNEL,
                        message_id=target_msg_id,
                        caption=new_caption
                    )
                    
                    print(f"✅ تم تحديث الحلقة {ep_num} للمسلسل: {old_title} -> {new_title}")
                    
            except Exception as e:
                print(f"❌ خطأ في تحديث الحلقة {v_id}: {e}")
        
        # تحديث عنوان المسلسل في قاعدة البيانات
        if source_message_id:
            db_query("""
                UPDATE videos 
                SET title = %s 
                WHERE source_message_id = %s
            """, (new_title, source_message_id), fetch=False)
        else:
            db_query("""
                UPDATE videos 
                SET title = %s 
                WHERE title = %s
            """, (new_title, old_title), fetch=False)
        
        return True
        
    except Exception as e:
        print(f"❌ خطأ في تحديث العنوان: {e}")
        return False

# ===== معالج تعديل الرسائل في المصدر =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation | filters.photo))
async def handle_edited_message(client, edited_message):
    """معالجة تعديل الرسائل في المصدر"""
    try:
        message = edited_message
        source_id = message.id
        
        # البحث عن الفيديو في قاعدة البيانات
        video_info = db_query("""
            SELECT title, target_message_id 
            FROM videos 
            WHERE source_message_id = %s
        """, (source_id,))
        
        if not video_info:
            return
        
        old_title = video_info[0][0]
        
        # استخراج العنوان الجديد
        if message.caption:
            new_title = clean_series_title(message.caption)
        elif message.text:
            new_title = clean_series_title(message.text)
        else:
            return
        
        if new_title and new_title != old_title:
            print(f"📝 تم اكتشاف تعديل: {old_title} -> {new_title}")
            
            # تحديث العنوان في جميع القنوات
            success = await update_series_title_in_channels(
                client, 
                old_title, 
                new_title, 
                source_id
            )
            
            if success:
                # إرسال إشعار للمشرف
                await client.send_message(
                    ADMIN_ID,
                    f"🔄 **تم تحديث عنوان المسلسل تلقائياً:**\n\n"
                    f"📌 القديم: `{old_title}`\n"
                    f"📌 الجديد: `{new_title}`\n"
                    f"🆔 المصدر: `{source_id}`"
                )
                
    except Exception as e:
        print(f"❌ خطأ في معالجة التعديل: {e}")
        await client.send_message(
            ADMIN_ID,
            f"⚠️ **خطأ في التحديث التلقائي:**\n`{e}`"
        )

# ===== تعديل معالج استقبال الفيديو لتخزين source_message_id =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    d = media.duration if media and hasattr(media, 'duration') else 0
    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    
    # تخزين مع source_message_id
    db_query("""
        INSERT INTO videos (v_id, status, duration, source_message_id) 
        VALUES (%s, 'waiting', %s, %s) 
        ON CONFLICT (v_id) DO UPDATE 
        SET status='waiting', duration=%s, source_message_id=%s
    """, (v_id, dur, message.id, dur, message.id), fetch=False)
    
    await message.reply_text(f"✅ تم المرفق ({dur}). أرسل البوستر الآن.")

# ===== تعديل معالج استقبال رقم الحلقة لتخزين target_message_id =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("""
        SELECT v_id, title, poster_id, quality, duration, source_message_id 
        FROM videos 
        WHERE status='awaiting_ep' 
        ORDER BY v_id DESC LIMIT 1
    """)
    if not res: return
    v_id, title, p_id, q, dur, source_id = res[0]
    ep_num = int(message.text)
    
    # تخزين رقم الحلقة وتحديث الحالة
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    b_info = await client.get_me()
    caption = f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n<b>الجودة: [{q}]</b>\n<b>المدة: [{dur}]</b>"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{b_info.username}?start={v_id}")]])
    
    try:
        # نشر في القناة وتخزين target_message_id
        sent_message = await client.send_photo(
            chat_id=int(PUBLIC_POST_CHANNEL), 
            photo=p_id, 
            caption=caption, 
            reply_markup=markup
        )
        
        # تحديث target_message_id في قاعدة البيانات
        db_query("""
            UPDATE videos 
            SET target_message_id = %s 
            WHERE v_id = %s
        """, (sent_message.id, v_id), fetch=False)
        
        # تخزين في جدول published_messages
        db_query("""
            INSERT INTO published_messages (source_message_id, target_message_id, target_channel_id, series_title)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_message_id, target_channel_id) 
            DO UPDATE SET target_message_id = %s, last_updated = CURRENT_TIMESTAMP
        """, (source_id, sent_message.id, PUBLIC_POST_CHANNEL, title, sent_message.id), fetch=False)
        
        await message.reply_text("🚀 تم النشر بنجاح.")
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ في النشر: {e}")

# ===== أمر يدوي للتحديث =====
@app.on_message(filters.command("update_series") & filters.private)
async def manual_update_command(client, message):
    """أمر يدوي لتحديث مسلسل (للمشرف فقط)"""
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply_text(
            "❌ استخدام: /update_series العنوان_القديم العنوان_الجديد\n"
            "أو: /update_series source_id العنوان_الجديد"
        )
        return
    
    try:
        if args[1].isdigit():
            # تحديث بمصدر محدد
            source_id = int(args[1])
            new_title = args[2]
            success = await update_series_title_in_channels(client, None, new_title, source_id)
            msg = f"تم تحديث المسلسل للمصدر {source_id} بـ {new_title}"
        else:
            # تحديث بكل العناوين
            old_title = args[1]
            new_title = args[2]
            success = await update_series_title_in_channels(client, old_title, new_title)
            msg = f"تم تحديث المسلسل {old_title} -> {new_title}"
        
        if success:
            await message.reply_text(f"✅ {msg}")
        else:
            await message.reply_text("❌ لم يتم العثور على مسلسل للتحديث")
            
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

# ===== أمر لعرض حالة المسلسلات =====
@app.on_message(filters.command("series_status") & filters.private)
async def series_status_command(client, message):
    """عرض حالة المسلسلات (للمشرف فقط)"""
    if message.from_user.id != ADMIN_ID:
        return
    
    # عرض آخر 10 مسلسلات مضافة
    series = db_query("""
        SELECT title, COUNT(*) as episodes, 
               MIN(ep_num) as first_ep, MAX(ep_num) as last_ep
        FROM videos 
        WHERE status='posted' 
        GROUP BY title 
        ORDER BY MAX(v_id) DESC 
        LIMIT 10
    """)
    
    if not series:
        await message.reply_text("لا توجد مسلسلات بعد")
        return
    
    text = "📊 **آخر المسلسلات المضافة:**\n\n"
    for title, count, first, last in series:
        text += f"🎬 {title}\n"
        text += f"   📦 {count} حلقة (من {first} إلى {last})\n\n"
    
    await message.reply_text(text)

# ===== باقي الكود كما هو (بدون تغيير) =====
# MAIN_MENU, search_handler, start_handler, get_stats, etc...
MAIN_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton("🔍 كيف أبحث عن مسلسل؟")], [KeyboardButton("✍️ طلب مسلسل جديد")]],
    resize_keyboard=True
)

@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats", "update_series", "series_status"]))
async def search_handler(client, message):
    user_mention = message.from_user.mention
    user_id = message.from_user.id

    if message.text == "🔍 كيف أبحث عن مسلسل؟":
        await message.reply_text("🔎 اكتب اسم المسلسل مباشرة (مثال: الكينج) وسأعرض لك النتائج المتوفرة.")
        return

    if message.text == "✍️ طلب مسلسل جديد":
        await message.reply_text("📥 أرسل اسم المسلسل الذي تريده الآن (سيتم إرساله للإدارة مباشرة):", reply_markup=ForceReply(selective=True))
        return

    if message.reply_to_message and "أرسل اسم المسلسل" in message.reply_to_message.text:
        await client.send_message(ADMIN_ID, f"🆕 **طلب مسلسل جديد:**\n\n👤 من: {user_mention}\n🆔 الآيدي: `{user_id}`\n🎬 المسلسل: **{message.text}**")
        await message.reply_text("✅ تم إرسال طلبك للإدارة، سنوفره لك في أقرب وقت.")
        return
        
    query = normalize_text(message.text)
    if len(query) < 2: return
    
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if query in normalize_text(t[0])]
    
    if matches:
        btns = []
        bot_info = await client.get_me()
        for m in list(dict.fromkeys(matches))[:10]:
            first_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC LIMIT 1", (m,))
            if first_ep:
                btns.append([InlineKeyboardButton(f"🎬 {m}", url=f"https://t.me/{bot_info.username}?start={first_ep[0][0]}")])
        
        await message.reply_text(f"🔍 نتائج البحث عن '{message.text}':", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await client.send_message(ADMIN_ID, f"⚠️ **بحث فاشل (غير متوفر):**\n\n👤 من: {user_mention}\n🔍 الكلمة: `{message.text}`")
        await message.reply_text("❌ لم يتم العثور على نتائج.\nتم إبلاغ الإدارة بطلبك وسنحاول توفيره قريباً.")

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: <b>{q}</b>. أرسل الآن رقم الحلقة:")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"مرحباً بك يا <b>{escape(message.from_user.first_name)}</b>! ابحث عن مسلسلك هنا 👇", reply_markup=MAIN_MENU)
        return
        
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if not res: return
    
    title, ep, q, dur = res[0]
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    
    btns = await get_episodes_markup(title, v_id)
    is_sub = await check_subscription(client, message.from_user.id)
    
    cap = (
        f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n"
        f"<b>🎞️ رقم الحلقة : {ep}</b>\n"
        f"<b>💿 الجودة : {q}</b>\n"
        f"<b>⏳ المدة : {dur}</b>"
    )

    if not is_sub:
        cap += f"\n\n⚠️ <b>يجب الانضمام للقناة لمتابعة الحلقات 👇</b>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)]] + btns)
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=markup)
    except:
        await message.reply_text(f"🎬 {title} - حلقة {ep}")

@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: return
    top = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 10")
    text = "📊 <b>تقرير الأداء (الأكثر مشاهدة):</b>\n\n"
    for i, r in enumerate(top or [], 1):
        text += f"{i}. {r[0]} (ح {r[1]}) ← {r[2]} مشاهدة\n"
    await message.reply_text(text)

if __name__ == "__main__":
    app.run()
