import os
import psycopg2
import logging
import re
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

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307 
FORCE_SUB_CHANNEL = -1003894735143 
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
BOT_USERNAME = None  # سيتم تعيينه عند بدء البوت

# ===== محرك البحث الذكي (تطبيع النص) =====
def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ة]', 'ه', text)
    text = re.sub(r'[ى]', 'ي', text)
    text = re.sub(r'[ئؤ]', 'ء', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def clean_series_title(text):
    if not text: return "مسلسل"
    cleaned = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text)
    return cleaned.strip()

def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== نظام التنبيهات للأدمن =====
async def notify_admin(content, report_type="alert"):
    prefix = "⚠️ **بلاغ عن عطل**" if report_type == "alert" else "📝 **طلب مسلسل جديد**"
    try:
        await app.send_message(ADMIN_ID, f"{prefix}\n\n{content}")
    except Exception as e:
        logging.error(f"Failed to notify admin: {e}")

# ===== بدء البوت وحفظ اسم المستخدم =====
@app.on_startup
async def startup_handler(client, _):
    global BOT_USERNAME
    try:
        me = await client.get_me()
        BOT_USERNAME = me.username
        logging.info(f"✅ البوت بدأ: @{BOT_USERNAME}")
    except Exception as e:
        logging.error(f"Failed to get bot username: {e}")

# ===== نظام البحث للأعضاء =====
@app.on_message(filters.private & ~filters.command(["start"]))
async def search_handler(client, message):
    user_query = message.text.strip()
    if not user_query or len(user_query) < 2:
        await message.reply_text("📝 أرسل اسم المسلسل الذي تبحث عنه.")
        return
    
    norm_query = normalize_text(user_query)
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [t[0] for t in (res or []) if norm_query in normalize_text(t[0])]
    
    if not matches:
        await message.reply_text("🔍 لم أجد المسلسل في المكتبة، تم إرسال طلبك للإدارة.")
        await notify_admin(f"👤 {message.from_user.mention} طلب: `{user_query}`", "request")
        return

    buttons = [[InlineKeyboardButton(f"🎬 {t}", callback_data=f"list_eps_{t[:30]}")] for t in matches[:10]]
    await message.reply_text("✨ نتائج البحث:", reply_markup=InlineKeyboardMarkup(buttons))

# ===== معالجة اختيار الحلقات والجودات =====
@app.on_callback_query(filters.regex("^list_eps_|^sel_q_|^get_vid_"))
async def cb_handler(client, cb):
    try:
        if cb.data.startswith("list_eps_"):
            title_part = cb.data.replace("list_eps_", "")
            res = db_query("SELECT DISTINCT ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY ep_num ASC", (f"{title_part}%",))
            if not res: 
                return await cb.answer("❌ لا توجد حلقات متاحة.")
            
            buttons, row = [], []
            for (ep,) in res:
                row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"sel_q_{title_part}_{ep}"))
                if len(row) == 3: 
                    buttons.append(row)
                    row = []
            if row: 
                buttons.append(row)
            
            await cb.message.edit_text(f"📺 **حلقات المسلسل:**", reply_markup=InlineKeyboardMarkup(buttons))

        elif cb.data.startswith("sel_q_"):
            # استخراج العنوان ورقم الحلقة بشكل آمن
            data = cb.data.replace("sel_q_", "")
            parts = data.rsplit("_", 1)  # تقسيم من النهاية للحصول على رقم الحلقة
            
            if len(parts) != 2:
                return await cb.answer("❌ خطأ في البيانات.")
            
            title_part, ep = parts
            
            res = db_query("SELECT quality, v_id FROM videos WHERE title LIKE %s AND ep_num=%s AND status='posted'", (f"{title_part}%", ep))
            
            if not res:
                return await cb.answer("❌ لا توجد جودات متاحة.")
            
            buttons = [[InlineKeyboardButton(f"💿 {q}", callback_data=f"get_vid_{v_id}")] for q, v_id in res]
            await cb.message.edit_text(f"🎬 **الحلقة {ep}**\n\nاختر الجودة:", reply_markup=InlineKeyboardMarkup(buttons))

        elif cb.data.startswith("get_vid_"):
            v_id = cb.data.replace("get_vid_", "")
            res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s AND status='posted'", (v_id,))
            
            if not res:
                return await cb.answer("❌ الفيديو غير متاح.")
            
            await send_video_final(client, cb.message.chat.id, cb.from_user.id, v_id, *res[0])
            await cb.answer("✅ جاري الإرسال...")
    
    except Exception as e:
        logging.error(f"Callback error: {e}")
        await cb.answer("❌ حدث خطأ، حاول لاحقاً.")

# ===== استقبال الفيديو من قناة المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    if not message.caption:
        return await message.reply_text("❌ يجب كتابة اسم المسلسل في وصف الفيديو.")
    
    series_name = clean_series_title(message.caption)
    media = message.video or message.animation or message.document
    
    # حساب المدة
    d = getattr(media, 'duration', 0) or 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}" if d else "00:00:00"

    db_query("""
        INSERT INTO videos (v_id, title, status, duration) VALUES (%s, %s, 'waiting', %s) 
        ON CONFLICT (v_id) DO UPDATE SET title=%s, status='waiting', duration=%s
    """, (v_id, series_name, dur, series_name, dur), fetch=False)
    
    await message.reply_text(f"✅ تم حفظ: <b>{series_name}</b>\n⏳ المدة: {dur}\n\nأرسل البوستر الآن:", parse_mode=ParseMode.HTML)

# ===== استقبال البوستر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id, title FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: 
        return await message.reply_text("❌ أرسل الفيديو أولاً.")
    
    v_id, title = res[0]
    db_query("UPDATE videos SET poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (message.photo.file_id, v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), 
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), 
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
    ]])
    await message.reply_text(f"📌 <b>{title}</b>\n\nاختر الجودة:", reply_markup=markup, parse_mode=ParseMode.HTML)

# ===== تحديد الجودة =====
@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    try:
        parts = cb.data.split("_")
        q = parts[1]
        v_id = "_".join(parts[2:])  # في حالة كانت v_id تحتوي على _
        
        db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
        await cb.message.edit_text(f"✅ الجودة: <b>{q}</b>\n\nأرسل رقم الحلقة (أرقام فقط):", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Quality setting error: {e}")
        await cb.answer("❌ حدث خطأ.")

# ===== استقبال رقم الحلقة =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep_num(client, message):
    # تأكد أن الرسالة أرقام فقط
    if not message.text.strip().isdigit():
        return
    
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res:
        await message.reply_text("❌ لم يتم العثور على فيديو في انتظار رقم الحلقة.")
        return
    
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text.strip()
    
    # حفظ الحلقة
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    # نشر في القناة العامة
    try:
        await publish_to_public(client, title, ep_num, p_id, dur)
        await message.reply_text(f"🚀 تم نشر الحلقة {ep_num} من <b>{title}</b> بنجاح!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Publishing error: {e}")
        await message.reply_text(f"⚠️ تم حفظ الحلقة لكن حدث خطأ في النشر: {e}")
        await notify_admin(f"🚨 خطأ في النشر: {title} - حلقة {ep_num}\n{e}")

async def publish_to_public(client, title, ep_num, poster_id, duration):
    # جلب جميع الجودات
    res = db_query("SELECT quality, v_id FROM videos WHERE title=%s AND ep_num=%s AND status='posted'", (title, ep_num))
    
    if not res or not BOT_USERNAME:
        raise Exception("لا توجد بيانات أو لم يتم تحديد اسم البوت.")
    
    buttons = [[InlineKeyboardButton(f"🎬 {q}", url=f"https://t.me/{BOT_USERNAME}?start={vid}")] for q, vid in res]
    markup = InlineKeyboardMarkup(buttons)
    
    caption = f"🎬 <b>{title}</b>\n\n📌 الحلقة: {ep_num}\n⏳ المدة: {duration}\n\n🍿 مشاهدة ممتعة!"
    
    try:
        await client.send_photo(PUBLIC_POST_CHANNEL, poster_id, caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Failed to send photo: {e}")
        raise

# ===== إرسال الفيديو النهائي =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    try:
        # التحقق من الاشتراك الإجباري
        try:
            member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
            if member.status in ["left", "kicked"]:
                return await client.send_message(chat_id, f"❌ يجب الاشتراك أولاً:\n{FORCE_SUB_LINK}", parse_mode=ParseMode.HTML)
        except Exception:
            return await client.send_message(chat_id, f"❌ يجب الاشتراك أولاً:\n{FORCE_SUB_LINK}", parse_mode=ParseMode.HTML)
        
        # إرسال الفيديو
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=f"📺 <b>{title}</b>\n🎞️ حلقة: {ep}\n💿 جودة: {q}\n⏳ {dur}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Video sending error: {e}")
        await notify_admin(f"🚨 عطل في إرسال الفيديو:\nالمسلسل: {title}\nالحلقة: {ep}\nالخطأ: {e}")
        await client.send_message(chat_id, "⚠️ الحلقة معطلة حالياً، تم إبلاغ الإدارة.")

@app.on_message(filters.command("start") & filters.private)
async def start_h(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s AND status='posted'", (v_id,))
        if res: 
            await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
        else:
            await message.reply_text("❌ الفيديو غير متاح.")
    else:
        await message.reply_text(f"👋 أهلاً <b>{message.from_user.first_name}</b>!\n\n🔍 ابحث عن مسلسلك الآن.", parse_mode=ParseMode.HTML)

if __name__ == "__main__":
    app.run()
