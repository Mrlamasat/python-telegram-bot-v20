import os
import sqlite3
import logging
import io
from PIL import Image
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

ADMIN_CHANNEL = -1003547072209 
TEST_CHANNEL = "@khofkrjrnrqnrnta" 

app = Client("CinemaBot_Final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- إدارة قاعدة البيانات ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect("cinema.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone: res = cursor.fetchone()
    if fetchall: res = cursor.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

# --- دالة عرض الحلقة مع أزرار الحلقات الأخرى ---
async def send_episode_details(client, chat_id, v_id):
    # 1. جلب بيانات الحلقة الحالية
    ep = db_query("SELECT poster_id, title, ep_num, duration, quality FROM episodes WHERE v_id=?", (v_id,), fetchone=True)
    
    if not ep:
        return await client.send_message(chat_id, "❌ عذراً، هذه الحلقة غير موجودة حالياً.")

    poster_id, title, ep_num, duration, quality = ep

    try:
        # 2. إرسال الفيديو أولاً (بوضع الحماية لمنع التوجيه)
        await client.copy_message(chat_id, ADMIN_CHANNEL, int(v_id), protect_content=True)

        # 3. جلب كافة الحلقات التي لها نفس البوستر للترتيب
        all_eps = db_query("SELECT v_id, ep_num FROM episodes WHERE poster_id=? ORDER BY ep_num ASC", (poster_id,), fetchall=True)

        # 4. بناء لوحة الأزرار
        buttons = []
        row = []
        for vid, num in all_eps:
            # تمييز الحلقة الحالية بنجمة
            label = f"⭐ {num}" if str(vid) == str(v_id) else f"{num}"
            row.append(InlineKeyboardButton(label, callback_data=f"go_{vid}"))
            
            # كل 4 أزرار في سطر واحد
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row: buttons.append(row)

        # 5. تنسيق الرسالة النصية أسفل الفيديو
        header = f"🎬 **{title}**\n" if title and title.strip() else ""
        caption = (
            f"{header}"
            f"📦 **حلقة رقم:** {ep_num}\n"
            f"⏱ **المده:** {duration}\n"
            f"✨ **الجودة:** {quality}\n\n"
            f"📖 **شاهد باقي الحلقات:**"
        )

        await client.send_message(chat_id, caption, reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        logger.error(f"Error sending episode: {e}")
        await client.send_message(chat_id, "⚠️ حدث خطأ أثناء عرض الحلقة.")

# --- معالجة التنقل بين الحلقات (Callback Query) ---
@app.on_callback_query(filters.regex(r"^go_"))
async def on_navigate(client, query):
    v_id = query.data.split("_")[1]
    # حذف الرسالة القديمة لعرض الجديدة (يعطي شعور بالتنقل)
    await query.message.delete()
    await send_episode_details(client, query.from_user.id, v_id)

# --- معالجة أمر البداية /start ---
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        await send_episode_details(client, message.chat.id, v_id)
    else:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name} في بوت المسلسلات.")

# --- خطوات الرفع (كما هي في الكود السابق) ---
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document) & ~filters.photo & ~filters.sticker)
async def on_video(client, message):
    v_id = str(message.id)
    duration_sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    duration = f"{duration_sec // 60}:{duration_sec % 60:02d}"
    db_query("INSERT OR REPLACE INTO temp_upload (chat_id, v_id, duration, step) VALUES (?, ?, ?, ?)", 
             (ADMIN_CHANNEL, v_id, duration, "awaiting_poster"), commit=True)
    await message.reply_text("✅ تم استلام الفيديو\n🖼 أرسل البوستر الآن:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.sticker | filters.document))
async def on_poster(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_poster": return
    p_id = message.photo.file_id if message.photo else (message.sticker.file_id if message.sticker else message.document.file_id)
    title = message.caption if message.caption else ""
    db_query("UPDATE temp_upload SET poster_id = ?, title = ?, step = ? WHERE chat_id = ?", 
             (p_id, title, "awaiting_ep_num", ADMIN_CHANNEL), commit=True)
    await message.reply_text("🔢 أرسل رقم الحلقة:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command("start"))
async def on_text(client, message):
    res = db_query("SELECT step FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not res or res[0] != "awaiting_ep_num": return
    if not message.text.isdigit(): return
    db_query("UPDATE temp_upload SET ep_num=?, step=? WHERE chat_id=?", (int(message.text), "awaiting_quality", ADMIN_CHANNEL), commit=True)
    btns = InlineKeyboardMarkup([[InlineKeyboardButton("720p", callback_data="q_720p"), InlineKeyboardButton("1080p", callback_data="q_1080p")]])
    await message.reply_text("✨ اختر الجودة للنشر:", reply_markup=btns)

@app.on_callback_query(filters.regex(r"^q_"))
async def on_quality(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT v_id, poster_id, title, ep_num, duration FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), fetchone=True)
    if not data: return
    v_id, poster_id, title, ep_num, duration = data

    db_query("INSERT OR REPLACE INTO episodes VALUES (?, ?, ?, ?, ?, ?)", (v_id, poster_id, title, ep_num, duration, quality), commit=True)
    db_query("DELETE FROM temp_upload WHERE chat_id=?", (ADMIN_CHANNEL,), commit=True)

    watch_link = f"https://t.me/{(await client.get_me()).username}?start={v_id}"
    caption = (f"🎬 **{title}**\n" if title else "") + f"🔢 الحلقة: {ep_num}\n⏱ المدة: {duration}\n✨ الجودة: {quality}\n\n📥 اضغط الزر لمشاهدة الحلقة"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ فتح الحلقة الآن", url=watch_link)]])

    try:
        file_path = await client.download_media(poster_id)
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            bio = io.BytesIO()
            bio.name = "poster.png"
            img.save(bio, "PNG")
            bio.seek(0)
            await client.send_photo(TEST_CHANNEL, photo=bio, caption=caption, reply_markup=markup)
        if os.path.exists(file_path): os.remove(file_path)
    except:
        await client.send_photo(TEST_CHANNEL, photo=poster_id, caption=caption, reply_markup=markup)

    await query.message.edit_text(f"🚀 تم النشر بنجاح!")

app.run()
