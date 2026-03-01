import os
import psycopg2
import logging
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== الإعدادات الأساسية =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHtplbFHhJ-4fatqVWXQowETrKg-u0cr0Q")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591  # الآيدي الخاص بك يا محمد

# --- معرفات القنوات ---
SOURCE_CHANNEL = -1003547072209  
FORCE_SUB_CHANNEL = -1003554018307  
FORCE_SUB_LINK = "https://t.me/+PyUeOtPN1fs0NDA0"  
PUBLIC_POST_CHANNEL = "@ramadan2206"  

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

# ===== الدوال المساعدة =====
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text: return "مسلسل"
    return re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text).strip()

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"📍 {ep_num}" if v_id == current_v_id else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    return buttons

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except Exception: return False

# ===== إرسال الفيديو النهائي مع عداد المشاهدات =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    # تحديث عداد المشاهدات تلقائياً
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    
    btns = await get_episodes_markup(title, v_id)
    is_subscribed = await check_subscription(client, user_id)
    safe_title = obfuscate_visual(title)

    # التنسيق العريض مع الأيقونات المتحركة (GIF) - شغل الغلابة المحترفين
    info_text = (
        f"<b><a href='https://s6.gifyu.com/images/S6atp.gif'>&#8205;</a>📺 المسلسل : {safe_title}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6at3.gif'>&#8205;</a>🎞️ رقم الحلقة : {ep}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6atZ.gif'>&#8205;</a>💿 الجودة : {q}</b>\n"
        f"<b><a href='https://s6.gifyu.com/images/S6at7.gif'>&#8205;</a>⏳ المدة : {dur}</b>"
    )

    cap = f"{info_text}\n\n🍿 <b>مشاهدة ممتعة نتمناها لكم!</b>"

    if not is_subscribed:
        cap += "\n\n⚠️ <b>انضم للقناة البديلة لمتابعة الحلقات القادمة 👇</b>"
        button_text = "📥 اضغط هنا للانضمام (مهم)"
        new_channel_btn = [InlineKeyboardButton(button_text, url=FORCE_SUB_LINK)]
        reply_markup = InlineKeyboardMarkup([new_channel_btn] + (btns if btns else []))
    else:
        reply_markup = InlineKeyboardMarkup(btns) if btns else None

    await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, parse_mode="HTML", reply_markup=reply_markup)

# ===== معالجة أمر الإحصائيات (حصري لمحمد) =====
@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID:
        return # يتجاهل أي شخص آخر
        
    # جلب أفضل 10 حلقات مشاهدة
    top_eps = db_query("SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 10")
    
    text = "📊 <b>تقرير الأداء والمشاهدات:</b>\n\n"
    if top_eps:
        for i, row in enumerate(top_eps, 1):
            text += f"{i}. 🎬 <b>{row[0]}</b>\n└ حلقة {row[1]} ← 👤 <b>{row[2]} مشاهدة</b>\n\n"
    else:
        text += "لا توجد بيانات مشاهدة حتى الآن."
    
    await message.reply_text(text, parse_mode="HTML")

# ===== استقبال الفيديو والبوستر (نفس المنطق السابق) =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation
    dur = "00:00:00"
    if media and hasattr(media, 'duration'):
        d = media.duration
        dur = f"{d//3600:02}:{(d%3600)//60:02}:{d%60:02}"
        
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, "waiting", dur, dur), fetch=False)
    await message.reply_text(f"✅ تم استلام المرفق.\n⏱ المدة: <b>{dur}</b>\nأرسل البوستر الآن.", parse_mode="HTML")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title = res[0][0], clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: <b>{title}</b>\nاختر الجودة:", reply_markup=markup, parse_mode="HTML")

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, callback_query):
    _, q, v_id = callback_query.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await callback_query.message.edit_text(f"✅ الجودة: <b>{q}</b>\nأرسل الآن رقم الحلقة:", parse_mode="HTML")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, poster_id, quality, duration = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    bot_info = await client.get_me()
    caption = f"🎬 <b>{obfuscate_visual(title)}</b>\n\n<b>الحلقة:</b> <b>[{ep_num}]</b>\n<b>الجودة:</b> <b>[{quality}]</b>\n<b>المدة:</b> <b>[{duration}]</b>\n\nنتمنى لكم مشاهده ممتعة."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهده الحلقة", url=f"https://t.me/{bot_info.username}?start={v_id}")]])
    await client.send_photo(PUBLIC_POST_CHANNEL, poster_id, caption=caption, reply_markup=markup, parse_mode="HTML")
    await message.reply_text(f"🚀 تم النشر بنجاح.")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا <b>{message.from_user.first_name}</b>!", parse_mode="HTML")
        return
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if not res: return
    await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])

if __name__ == "__main__":
    app.run()
