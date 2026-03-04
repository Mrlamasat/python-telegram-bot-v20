import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# المعرفات (تأكد أنها مطابقة لقنواتك)
SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307 
FORCE_SUB_CHANNEL = -1003894735143 

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text.replace(" ", "  ")))

# ===== 1. استقبال الفيديو (بداية العملية) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    # الحصول على المدة
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') and media.duration else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    
    # حفظ مبدئي في القاعدة
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    
    await message.reply_text(f"✅ تم استلام الملف بنجاح.\n⏳ المدة: {dur}\n\n**الآن أرسل البوستر (الصورة) واكتب اسم المسلسل في وصفها.**", quote=True)

# ===== 2. استقبال البوستر (الخطوة الثانية) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    # البحث عن آخر فيديو ينتظر بوستر
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res:
        return # لا يوجد فيديو ينتظر

    v_id = res[0][0]
    title = message.caption
    
    if not title:
        await message.reply_text("⚠️ خطأ: يجب كتابة اسم المسلسل في وصف الصورة (Caption) لكي أستمر!", quote=True)
        return

    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), 
         InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), 
         InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]
    ])
    await message.reply_text(f"📌 تم اعتماد الاسم: {title}\n\n**اختر الجودة المطلوبة الآن:**", reply_markup=markup, quote=True)

# ===== 3. اختيار الجودة (الخطوة الثالثة) =====
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    data = cb.data.split("_")
    q = data[1]
    v_id = data[2]
    
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ اخترت جودة: {q}\n\n**أرسل الآن رقم الحلقة فقط (مثلاً: 15):**")

# ===== 4. استقبال رقم الحلقة والنشر (الخطوة الأخيرة) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text)
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text
    
    # تنسيق الاسم بالتنقيط
    safe_title = obfuscate_visual(escape(title))
    caption = (
        f"🎬 <b>{safe_title}</b>\n\n"
        f"<b>الحلقة: [{ep_num}]</b>\n"
        f"<b>الجودة: [{q}]</b>\n"
        f"<b>المدة: [{dur}]</b>\n\n"
        f"نتمنى لكم مشاهدة ممتعة."
    )
    
    me = await client.get_me()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    try:
        # النشر في القناة العامة
        post = await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
        
        # تحديث الحالة وحفظ ID المنشور للتعديل لاحقاً
        db_query("UPDATE videos SET ep_num=%s, status='posted', post_id=%s WHERE v_id=%s", (ep_num, post.id, v_id), fetch=False)
        
        await message.reply_text(f"🚀 تم النشر بنجاح في القناة!\nالمسلسل: {title}\nالحلقة: {ep_num}", quote=True)
    except Exception as e:
        await message.reply_text(f"❌ فشل النشر: {e}", quote=True)

# تشغيل البوت
app.run()
