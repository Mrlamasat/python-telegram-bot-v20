import os
import psycopg2
import logging
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ===== Logging =====
logging.basicConfig(level=logging.INFO)

# ===== Environment Variables =====
API_ID = int(os.environ.get("API_ID", 35405228))
API_HASH = os.environ.get("API_HASH", "dacba460d875d963bbd4462c5eb554d6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8579897728:AAHtplbFHhJ-4fatqVWXQowETrKg-u0cr0Q")
DATABASE_URL = os.environ.get("DATABASE_URL")

# --- القنوات المعدلة ---
SOURCE_CHANNEL = -1003547072209  
FORCE_SUB_CHANNEL = -1003554018307  # الآيدي الجديد الذي أرسلته
FORCE_SUB_LINK = "https://t.me/+PyUeOtPN1fs0NDA0"  # الرابط الجديد
PUBLIC_POST_CHANNEL = "@ramadan2206"  

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Database =====
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

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            status TEXT,
            ep_num INTEGER,
            quality TEXT,
            duration TEXT
        )
    """, fetch=False)

init_db()

# ===== Helpers =====

def obfuscate_visual(text):
    """تشفير بصري بوضع نقاط بين الحروف"""
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
    except UserNotParticipant: return False
    except Exception as e:
        logging.error(f"Subscription Check Error: {e}")
        return True

# ===== Handlers =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    dur = f"{message.video.duration // 60} دقيقة" if message.video else "غير محدد"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, %s, %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id, "waiting", dur), fetch=False)
    await message.reply_text("✅ تم استلام الفيديو. أرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = clean_series_title(message.caption)
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 المسلسل: {title}\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, callback_query):
    _, q, v_id = callback_query.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await callback_query.message.edit_text(f"✅ الجودة: {q}\nأرسل الآن رقم الحلقة الذي سيظهر للأعضاء:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, poster_id, quality, duration = res[0]
    ep_num = int(message.text)
    
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    safe_title = obfuscate_visual(title)
    bot_info = await client.get_me()
    caption = f"🎬 **{safe_title}**\n\nالحلقة [{ep_num}]\nالجودة [{quality}]\nالمده [{duration}]\n\nنتمنى لكم مشاهده ممتعة."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهده الحلقة", url=f"https://t.me/{bot_info.username}?start={v_id}")]])
    await client.send_photo(PUBLIC_POST_CHANNEL, poster_id, caption=caption, reply_markup=markup)
    await message.reply_text(f"🚀 تم النشر بنجاح بالحلقة رقم {ep_num}.")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}!")
        return
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if not res:
        await message.reply_text("❌ الحلقة غير متوفرة.")
        return
    
    # استخدام الدالة الموحدة للإرسال مع فحص الاشتراك
    await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])

@app.on_callback_query(filters.regex("^recheck_"))
async def recheck_cb(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    if await check_subscription(client, callback_query.from_user.id):
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res:
            await callback_query.message.delete()
            await send_video_final(client, callback_query.from_user.id, callback_query.from_user.id, v_id, *res[0])
    else:
        await callback_query.answer("⚠️ لم تشترك بعد في القناة الجديدة!", show_alert=True)

async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    # جلب أزرار الحلقات
    btns = await get_episodes_markup(title, v_id)
    
    # فحص الاشتراك في القناة الجديدة
    is_subscribed = await check_subscription(client, user_id)
    
    # تشفير مرئي للاسم
    safe_title = obfuscate_visual(title)
    
    if is_subscribed:
        # رسالة نظيفة للمشتركين
        cap = (
            f"🎬 **{safe_title}**\n\n"
            f"الحلقة [{ep}]\n"
            f"الجودة [{q}]\n"
            f"المده [{dur}]\n\n"
            f"نتمنى لكم مشاهده ممتعة."
        )
        reply_markup = InlineKeyboardMarkup(btns) if btns else None
    else:
        # رسالة تنبيه لغير المشتركين مع الزر العريض
        button_text = "📥 اضغط هنا للانضمام للقناة الجديدة (مهم)"
        new_channel_btn = [InlineKeyboardButton(button_text, url=FORCE_SUB_LINK)]
        final_keyboard = [new_channel_btn] + (btns if btns else [])
        
        warning_text = (
            "\n\n⚠️ **تنبيه هام جداً:**\n"
            "لقد تم نقل الحلقات القادمة إلى قناتنا البديلة. لضمان استمرار المشاهدة، يرجى الضغط على **الزر العريض بالأسفل** للانضمام مباشرة 👇👇"
        )
        
        cap = (
            f"🎬 **{safe_title}**\n\n"
            f"الحلقة [{ep}]\n"
            f"الجودة [{q}]\n"
            f"المده [{dur}]"
            f"{warning_text}\n\n"
            f"نتمنى لكم مشاهده ممتعة."
        )
        reply_markup = InlineKeyboardMarkup(final_keyboard)
    
    try:
        await client.copy_message(
            chat_id, 
            SOURCE_CHANNEL, 
            int(v_id), 
            caption=cap, 
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error copying message: {e}")
        # في حال عدم الاشتراك وفشل الإرسال المباشر (كإجراء احتياطي)
        if not is_subscribed:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 اشترك هنا", url=FORCE_SUB_LINK)],
                [InlineKeyboardButton("🔄 تحقق", callback_data=f"recheck_{v_id}")]
            ])
            await client.send_message(chat_id, "⚠️ يجب الاشتراك في القناة الجديدة لمشاهدة المحتوى:", reply_markup=markup)

if __name__ == "__main__":
    app.run()
