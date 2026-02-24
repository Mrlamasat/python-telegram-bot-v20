import os
import psycopg2
import logging
import re
import urllib.parse
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

# إعدادات القنوات الخاصة بك يا محمد
SOURCE_CHANNEL = -1003547072209      # قناة الرفع
FORCE_SUB_CHANNEL = -1003790915936   # قناة الاشتراك الإجباري
FORCE_SUB_LINK = "https://t.me/+KyrbVyp0QCJhZGU8"
PUBLIC_POST_CHANNEL = -1003678294148 # قناة النشر العامة

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
def encode_hidden(text):
    return "".join(["\u200b" + char for char in text])

def clean_series_title(text):
    if not text: return "مسلسل"
    # حذف كلمة حلقة أو الحلقة والأرقام والرموز الزائدة
    text = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', text)
    return text.strip()

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    if not res: return None
    
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    current_v_id = str(current_v_id)
    
    for v_id, ep_num in res:
        v_id_str = str(v_id)
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        
        label = f"▶️ {ep_num}" if v_id_str == current_v_id else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id_str}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    # --- أزرار المشاركة (تليجرام + واتساب) ---
    share_link = f"https://t.me/{bot_info.username}?start={current_v_id}"
    share_text = f"🍿 شاهد مسلسل: {title}\n🎬 متوفر الآن بجودة عالية عبر البوت الرسمي 👇"
    
    encoded_text = urllib.parse.quote(share_text)
    encoded_url = urllib.parse.quote(share_link)

    tg_share = f"https://t.me/share/url?url={encoded_url}&text={encoded_text}"
    wa_share = f"https://api.whatsapp.com/send?text={encoded_text}%20{encoded_url}"

    buttons.append([
        InlineKeyboardButton("📢 تليجرام", url=tg_share),
        InlineKeyboardButton("🟢 واتساب", url=wa_share)
    ])
    
    return buttons

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except UserNotParticipant: return False
    except: return True

# ===== المزامنة والتعديل التلقائي =====
@app.on_edited_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def sync_edited_video(client, message):
    v_id = str(message.id)
    caption = message.caption or ""
    title = clean_series_title(caption)
    
    ep_num = 1
    nums = re.findall(r'\d+', caption)
    if nums: ep_num = int(nums[0])
    
    db_query("""
        INSERT INTO videos (v_id, title, status, ep_num, quality) 
        VALUES (%s, %s, %s, %s, %s) 
        ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, status='posted'
    """, (v_id, title, 'posted', ep_num, 'HD', title, ep_num), fetch=False)
    
    await message.reply_text(f"🔄 تم تحديث الربط: **{title}** حلقة {ep_num}")

# ===== إجراءات النشر الجديد =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def receive_video(client, message):
    v_id = str(message.id)
    dur = f"{message.video.duration // 60} دقيقة" if message.video else "غير محدد"
    
    # قراءة الاسم والرقم من وصف الفيديو مباشرة
    caption = message.caption or ""
    title = clean_series_title(caption)
    ep_num = 1
    nums = re.findall(r'\d+', caption)
    if nums: ep_num = int(nums[0])

    db_query("""
        INSERT INTO videos (v_id, title, status, ep_num, duration) 
        VALUES (%s, %s, %s, %s, %s) 
        ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s, duration=%s, status='waiting'
    """, (v_id, title, "waiting", ep_num, dur, title, ep_num, dur), fetch=False)
    
    await message.reply_text(f"✅ تم استلام: **{title}** (حلقة {ep_num})\nأرسل البوستر الآن.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id, title FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, video_title = res[0]
    
    # استخدام وصف الصورة كاسم، أو الاسم المسحوب من الفيديو إذا كانت الصورة بدون وصف
    title = clean_series_title(message.caption) if message.caption else video_title
    
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), 
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), 
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
    ]])
    await message.reply_text(f"📌 المسلسل: {title}\nاختر الجودة:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, callback_query):
    _, q, v_id = callback_query.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await callback_query.message.edit_text(f"✅ الجودة: {q}\nأرسل الآن رقم الحلقة النهائي:")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, poster_id, quality, duration = res[0]
    ep_num = int(message.text)
    
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    bot_info = await client.get_me()
    caption = f"🎬 **{title}**\n\nالحلقة [{ep_num}]\nالجودة [{quality}]\nالمده [{duration}]\n\nنتمنى لكم مشاهده ممتعة."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهده الحلقة", url=f"https://t.me/{bot_info.username}?start={v_id}")]])
    
    await client.send_photo(PUBLIC_POST_CHANNEL, poster_id, caption=caption, reply_markup=markup)
    await message.reply_text(f"🚀 تم النشر بنجاح.")

# ===== Interaction (المشاهدة) =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(f"أهلاً بك يا محمد! أرسل رابط الحلقة لمشاهدتها.")
        return
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if not res:
        await message.reply_text("❌ الحلقة غير متوفرة.")
        return
    if not await check_subscription(client, message.from_user.id):
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك هنا", url=FORCE_SUB_LINK)], [InlineKeyboardButton("🔄 تحقق", callback_data=f"recheck_{v_id}")]])
        await message.reply_text("⚠️ يجب عليك الاشتراك أولاً لمشاهدة المحتوى.", reply_markup=markup)
        return
    await send_video_final(client, message.chat.id, v_id, *res[0])

@app.on_callback_query(filters.regex("^recheck_"))
async def recheck_cb(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    if await check_subscription(client, callback_query.from_user.id):
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res:
            await callback_query.message.delete()
            await send_video_final(client, callback_query.from_user.id, v_id, *res[0])
    else:
        await callback_query.answer("❌ لم تشترك بعد!", show_alert=True)

async def send_video_final(client, chat_id, v_id, title, ep, q, dur):
    btns = await get_episodes_markup(title, v_id)
    cap = f"الحلقة [{ep}]\nالجودة [{q}]\nالمده [{dur}]\n\n{encode_hidden(title)}\n\nنتمنى لكم مشاهده ممتعة."
    await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=InlineKeyboardMarkup(btns) if btns else None)

if __name__ == "__main__":
    app.run()
