import os
import psycopg2
import logging
import re
import asyncio
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# ===== الإعدادات الأساسية =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

# ===== معرفات القنوات (محدثة) =====
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003790915936
FORCE_SUB_LINK = "https://t.me/+nLtMePUz6lw3YzBk"  # الرابط الجديد
PUBLIC_POST_CHANNEL = -1003678294148

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
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
        cur.close()
        conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== دوال مساعدة =====
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    # إزالة أرقام الحلقات والروابط
    text = re.sub(r'(الحلقة|حلقة|#)?\s*\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'الجودة:.*|المدة:.*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_ep_num(text):
    if not text: return 0
    match = re.search(r'(?:الحلقة|حلقة|#)\s*(\d+)', text, re.IGNORECASE)
    return int(match.group(1)) if match else 0

def extract_quality(text):
    if not text: return "HD"
    match = re.search(r'(4K|HD|SD|720|1080|2160)', text, re.IGNORECASE)
    if match:
        q = match.group(1)
        if q == "720": return "HD"
        if q == "1080": return "FHD"
        if q == "2160": return "4K"
        return q.upper()
    return "HD"

# ===== جلب الحلقات المرتبطة بنفس البوستر =====
async def get_episodes_by_poster(video_id):
    """الحصول على جميع الحلقات التي تشارك نفس البوستر"""
    try:
        # جلب معلومات الفيديو الحالي
        video_data = db_query("""
            SELECT title, poster_id, poster_caption FROM videos 
            WHERE v_id = %s
        """, (str(video_id),))
        
        if not video_data:
            return []
        
        title, poster_id, poster_caption = video_data[0]
        
        # إذا كان هناك بوستر، نبحث بنفس البوستر
        if poster_id and poster_id != '':
            episodes = db_query("""
                SELECT v_id, ep_num FROM videos 
                WHERE poster_id = %s AND status = 'posted'
                ORDER BY ep_num ASC
            """, (poster_id,))
        else:
            # إذا لم نجد بوستر، نبحث بنفس العنوان
            episodes = db_query("""
                SELECT v_id, ep_num FROM videos 
                WHERE title = %s AND status = 'posted'
                ORDER BY ep_num ASC
            """, (title,))
        
        return episodes or []
        
    except Exception as e:
        logging.error(f"❌ خطأ في get_episodes_by_poster: {e}")
        return []

# ===== إنشاء أزرار الحلقات =====
async def get_episodes_markup(video_id, current_v_id):
    """إنشاء أزرار الحلقات المرتبطة بنفس البوستر"""
    episodes = await get_episodes_by_poster(video_id)
    
    if not episodes or len(episodes) <= 1:
        return []  # لا نعرض أزرار إذا كانت هناك حلقة واحدة
    
    buttons, row = [], []
    bot_info = await app.get_me()
    
    # ترتيب الحلقات تصاعدياً
    episodes.sort(key=lambda x: x[1])
    
    for v_id, ep_num in episodes:
        # علامة على الحلقة الحالية
        label = f"📍 {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        
        btn = InlineKeyboardButton(
            label, 
            url=f"https://t.me/{bot_info.username}?start={v_id}"
        )
        row.append(btn)
        
        # 5 أزرار في كل صف
        if len(row) == 5:
            buttons.append(row)
            row = []
    
    if row: 
        buttons.append(row)
    
    return buttons

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.error(f"❌ Subscription check error: {e}")
        return False

# ===== إرسال الفيديو النهائي للمستخدم =====
async def send_video_final(client, chat_id, user_id, v_id):
    # جلب بيانات الحلقة
    video_data = db_query("""
        SELECT title, ep_num, quality, duration, poster_id 
        FROM videos WHERE v_id = %s
    """, (v_id,))
    
    if not video_data:
        await client.send_message(chat_id, "❌ هذه الحلقة غير موجودة")
        return
    
    title, ep, q, dur, poster_id = video_data[0]
    
    # زيادة عداد المشاهدات
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    
    # الحصول على أزرار الحلقات
    btns = await get_episodes_markup(v_id, v_id)
    is_subscribed = await check_subscription(client, user_id)
    
    safe_title = obfuscate_visual(escape(title))
    info_text = (
        f"<b>📺 المسلسل : {safe_title}</b>\n"
        f"<b>🎞️ رقم الحلقة : {escape(str(ep))}</b>\n"
        f"<b>💿 الجودة : {escape(str(q))}</b>\n"
        f"<b>⏳ المدة : {escape(str(dur))}</b>"
    )
    cap = f"{info_text}\n\n🍿 <b>مشاهدة ممتعة!</b>"

    if not is_subscribed:
        cap += "\n\n⚠️ <b>انضم للقناة لمتابعة الحلقات القادمة 👇</b>"
        if btns:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]
            ] + btns)
        else:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]
            ])
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    try:
        await client.copy_message(
            chat_id, 
            SOURCE_CHANNEL, 
            int(v_id), 
            caption=cap, 
            parse_mode=ParseMode.HTML, 
            reply_markup=markup
        )
    except Exception as e:
        logging.error(f"❌ Send Error: {e}")
        await client.send_message(chat_id, f"🎬 {safe_title} - حلقة {ep}")

# ===== أمر الإحصائيات =====
@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID: 
        return
    
    top = db_query("""
        SELECT title, ep_num, views FROM videos 
        WHERE status='posted' 
        ORDER BY views DESC LIMIT 10
    """)
    
    text = "📊 <b>الأكثر مشاهدة:</b>\n\n"
    if top:
        for i, r in enumerate(top, 1):
            text += f"{i}. 🎬 <b>{escape(r[0])}</b>\n└ حلقة {r[1]} ← 👤 <b>{r[2]}</b>\n\n"
    else: 
        text += "لا توجد بيانات"
    
    await message.reply_text(text, parse_mode=ParseMode.HTML)

# ===== استقبال الفيديو من القناة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    d = media.duration if media and hasattr(media, 'duration') else 0
    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
    
    db_query("""
        INSERT INTO videos (v_id, status, duration) 
        VALUES (%s, 'waiting', %s) 
        ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s
    """, (v_id, dur, dur), fetch=False)
    
    await message.reply_text(f"✅ تم استلام الفيديو ({dur})", parse_mode=ParseMode.HTML)

# ===== استقبال البوستر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    # البحث عن فيديو في انتظار البوستر
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: 
        return
    
    v_id = res[0][0]
    title = clean_series_title(message.caption)
    
    db_query("""
        UPDATE videos SET title=%s, poster_id=%s, poster_caption=%s, status='awaiting_quality' 
        WHERE v_id=%s
    """, (title, message.photo.file_id, message.caption or '', v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"),
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
    ]])
    
    await message.reply_text(
        f"📌 <b>{escape(title)}</b>\nاختر الجودة:",
        reply_markup=markup, 
        parse_mode=ParseMode.HTML
    )

# ===== اختيار الجودة =====
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    
    await cb.message.edit_text(f"✅ الجودة: <b>{q}</b>\nأرسل رقم الحلقة:")

# ===== استقبال رقم الحلقة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats", "scan", "cleardb", "series"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): 
        return
    
    res = db_query("""
        SELECT v_id, title, poster_id, quality, duration FROM videos 
        WHERE status='awaiting_ep' 
        ORDER BY v_id DESC LIMIT 1
    """)
    
    if not res: 
        return
    
    v_id, title, p_id, q, dur = res[0]
    ep_num = int(message.text)
    
    # تحديث قاعدة البيانات
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    # نشر في القناة العامة
    b_info = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    
    caption = (
        f"🎬 <b>{safe_t}</b>\n\n"
        f"<b>الحلقة: {ep_num}</b>\n"
        f"<b>الجودة: {q}</b>\n"
        f"<b>المدة: {dur}</b>\n\n"
        f"نتمنى لكم مشاهدة ممتعة"
    )
    
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "▶️ مشاهدة", 
            url=f"https://t.me/{b_info.username}?start={v_id}"
        )
    ]])
    
    await client.send_photo(
        PUBLIC_POST_CHANNEL, 
        p_id, 
        caption=caption, 
        reply_markup=markup, 
        parse_mode=ParseMode.HTML
    )
    
    await message.reply_text("✅ تم النشر في القناة")

# ===== أمر المسح التلقائي =====
@app.on_message(filters.command("scan") & filters.private)
async def scan_command(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    msg = await message.reply_text("🔍 جاري مسح القناة...")
    
    try:
        stats = {'videos': 0, 'posters': 0}
        poster_cache = {}
        
        async for m in client.get_chat_history(SOURCE_CHANNEL, limit=5000):
            if m.photo:
                stats['posters'] += 1
                title = clean_series_title(m.caption or "")
                poster_cache[m.id] = {
                    'title': title,
                    'file_id': m.photo.file_id,
                    'caption': m.caption or ""
                }
            
            elif m.video or m.document:
                stats['videos'] += 1
                
                # البحث عن البوستر
                poster = None
                for pid in sorted(poster_cache.keys(), reverse=True):
                    if pid < m.id:
                        poster = poster_cache[pid]
                        break
                
                if poster:
                    media = m.video or m.animation
                    d = media.duration if media and hasattr(media, 'duration') else 0
                    dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
                    ep = extract_ep_num(m.caption or "")
                    q = extract_quality(m.caption or "")
                    
                    db_query("""
                        INSERT INTO videos (v_id, title, ep_num, quality, duration, poster_id, poster_caption, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'posted')
                        ON CONFLICT (v_id) DO UPDATE SET
                            title=EXCLUDED.title, 
                            ep_num=EXCLUDED.ep_num,
                            quality=EXCLUDED.quality, 
                            poster_id=EXCLUDED.poster_id,
                            poster_caption=EXCLUDED.poster_caption
                    """, (str(m.id), poster['title'], ep, q, dur, poster['file_id'], poster['caption'][:200]), fetch=False)
            
            await asyncio.sleep(0.1)
        
        await msg.edit_text(
            f"✅ <b>تم المسح بنجاح!</b>\n\n"
            f"📹 فيديوهات: {stats['videos']}\n"
            f"🖼️ بوسترات: {stats['posters']}",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

# ===== أمر مسح قاعدة البيانات =====
@app.on_message(filters.command("cleardb") & filters.private)
async def clear_db(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    db_query("DELETE FROM videos", fetch=False)
    await message.reply_text("✅ تم مسح قاعدة البيانات")

# ===== أمر إحصائيات المسلسلات =====
@app.on_message(filters.command("series") & filters.private)
async def series_stats(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    
    series = db_query("""
        SELECT title, COUNT(*) as eps, SUM(views) as views
        FROM videos GROUP BY title ORDER BY eps DESC LIMIT 20
    """)
    
    text = "📊 <b>المسلسلات:</b>\n\n"
    for title, eps, views in series:
        text += f"🎬 {escape(title[:30])}\n└ {eps} حلقة | {views or 0} مشاهدة\n\n"
    
    await message.reply_text(text, parse_mode=ParseMode.HTML)

# ===== بدء التشغيل =====
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(
            f"أهلاً <b>{escape(message.from_user.first_name)}</b>!", 
            parse_mode=ParseMode.HTML
        )
        return
    
    v_id = message.command[1]
    await send_video_final(client, message.chat.id, message.from_user.id, v_id)

if __name__ == "__main__":
    # إنشاء الجدول
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            quality TEXT DEFAULT 'HD',
            duration TEXT DEFAULT '00:00:00',
            poster_id TEXT,
            poster_caption TEXT,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """, fetch=False)
    
    logging.info("🚀 البوت يعمل...")
    app.run()
