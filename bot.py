import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from pyrogram.enums import ParseMode

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = "-1003547072209"
PUBLIC_POST_CHANNEL = "-1003554018307" 
FORCE_SUB_CHANNEL = "-1003894735143" 
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

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

# ===== وظائف التنسيق والبحث =====
def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'^(مسلسل|فيلم|برنامج|كرتون|انمي|افلام|مسلسلات)\s+', '', text)
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[ة]', 'ه', text)
    text = re.sub(r'[ى]', 'ي', text)
    return re.sub(r'\s+', ' ', text).strip()

def obfuscate_visual(text):
    if not text: return ""
    # التشفير بالنقاط الفاصلة
    return " . ".join(list(text.replace(" ", "  ")))

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return True 

MAIN_MENU = ReplyKeyboardMarkup([[KeyboardButton("🔍 كيف أبحث عن مسلسل؟")], [KeyboardButton("✍️ طلب مسلسل جديد")]], resize_keyboard=True)

# ===== وظيفة تحديث المنشور في القناة =====
async def update_public_post(client, v_id):
    res = db_query("SELECT title, ep_num, quality, duration, poster_id FROM videos WHERE v_id=%s AND status='posted'", (v_id,))
    if not res: return
    title, ep, q, dur, p_id = res[0]
    me = await client.get_me()
    
    caption = (
        f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n"
        f"<b>الحلقة: [{ep}]</b>\n"
        f"<b>الجودة: [{q}]</b>\n"
        f"<b>المدة: [{dur}]</b>\n\n"
        f"نتمنى لكم مشاهدة ممتعة."
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    # هنا نحاول تحديث الرسالة في القناة العامة (تحتاج لتخزين message_id المنشور في القناة لاحقاً إذا أردت تعديل المنشور نفسه)
    # حالياً سنكتفي بتحديث البيانات لكي تظهر صحيحة عند طلبها من البوت.

# ===== التعامل مع الرسائل المعدلة =====
@app.on_edited_message(filters.chat(int(SOURCE_CHANNEL)) & filters.photo)
async def handle_edit(client, message):
    new_title = message.caption or "مسلسل"
    v_id = db_query("SELECT v_id FROM videos WHERE poster_id=%s LIMIT 1", (message.photo.file_id,))
    if v_id:
        db_query("UPDATE videos SET title=%s WHERE v_id=%s", (new_title, v_id[0][0]), fetch=False)
        await message.reply_text(f"✅ تم تحديث اسم المسلسل إلى: {new_title}")

# ===== نظام الرفع والنشر =====
@app.on_message(filters.chat(int(SOURCE_CHANNEL)) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    media = message.video or message.animation or message.document
    d = media.duration if hasattr(media, 'duration') else 0
    dur = f"{d//3600:02d}:{(d%3600)//60:02d}:{d%60:02d}"
    db_query("INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s", (v_id, dur, dur), fetch=False)
    await message.reply_text(f"✅ تم المرفق ({dur}). أرسل البوستر الآن واكتب الاسم في الوصف.")

@app.on_message(filters.chat(int(SOURCE_CHANNEL)) & filters.photo)
async def receive_poster(client, message):
    res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id = res[0][0]
    title = message.caption or "مسلسل" # يأخذ الاسم من وصف الصورة
    db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"), InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"), InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")]])
    await message.reply_text(f"📌 تم اعتماد الاسم: {title}\nاختر الجودة الآن:", reply_markup=markup)

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    _, q, v_id = cb.data.split("_")
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"✅ الجودة: {q}. أرسل الآن رقم الحلقة:")

@app.on_message(filters.chat(int(SOURCE_CHANNEL)) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
    
    me = await client.get_me()
    caption = (
        f"🎬 <b>{obfuscate_visual(escape(title))}</b>\n\n"
        f"<b>الحلقة: [{ep_num}]</b>\n"
        f"<b>الجودة: [{q}]</b>\n"
        f"<b>المدة: [{dur}]</b>\n\n"
        f"نتمنى لكم مشاهدة ممتعة."
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    try:
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
        await message.reply_text(f"🚀 تم النشر بنجاح باسم: {title}")
    except Exception as e:
        await message.reply_text(f"❌ خطأ في النشر: {e}")

# ===== نظام البحث في البوت =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "stats"]))
async def private_handler(client, message):
    text = message.text
    if text == "🔍 كيف أبحث عن مسلسل؟":
        await message.reply_text("🔎 اكتب اسم المسلسل مباشرة (مثلاً: اثنين غيرنا) وسأبحث لك عنه.")
        return
    if text == "✍️ طلب مسلسل جديد":
        await message.reply_text("أرسل اسم المسلسل وسأبلغ الإدارة فوراً.")
        return

    if not await check_subscription(client, message.from_user.id):
        await message.reply_text("⚠️ اشترك أولاً للبحث.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        return

    query = normalize_text(text)
    if len(query) < 2: return
    res = db_query("SELECT DISTINCT title FROM videos WHERE status='posted'")
    matches = [row[0] for row in (res or []) if query in normalize_text(row[0])]
    if matches:
        btns = [[InlineKeyboardButton(f"🎬 {m}", callback_data=f"show_{m[:40]}")] for m in matches[:10]]
        await message.reply_text(f"🔍 نتائج البحث عن '{text}':", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await message.reply_text("❌ لم أجد المسلسل. تم إبلاغ الإدارة.")
        try: await client.send_message(ADMIN_ID, f"📥 طلب جديد: {text}")
        except: pass

@app.on_callback_query(filters.regex("^show_|^final_"))
async def cb_handler(client, cb):
    if cb.data.startswith("show_"):
        title = cb.data.replace("show_", "")
        res = db_query("SELECT v_id, ep_num FROM videos WHERE title LIKE %s AND status='posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (f"{title}%",))
        btns, row = [], []
        for vid, ep in (res or []):
            row.append(InlineKeyboardButton(f"حلقة {ep}", callback_data=f"final_{vid}"))
            if len(row) == 3: btns.append(row); row = []
        if row: btns.append(row)
        await cb.message.edit_text(f"📺 **{title}**\nاختر الحلقة:", reply_markup=InlineKeyboardMarkup(btns))
    elif cb.data.startswith("final_"):
        v_id = cb.data.replace("final_", "")
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res:
            title, ep, q, dur = res[0]
            # إرسال الفيديو النهائي للمستخدم
            cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n<b>💿 الجودة : {q}</b>\n<b>⏳ المدة : {dur}</b>"
            try:
                await client.copy_message(cb.message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=MAIN_MENU)
            except:
                await client.send_message(cb.message.chat.id, "❌ الملف غير متوفر.")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
        if res:
            title, ep, q, dur = res[0]
            cap = f"<b>📺 المسلسل : {obfuscate_visual(escape(title))}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n<b>💿 الجودة : {q}</b>\n<b>⏳ المدة : {dur}</b>"
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap, reply_markup=MAIN_MENU)
    else:
        await message.reply_text(f"أهلاً بك يا {message.from_user.first_name}!", reply_markup=MAIN_MENU)

if __name__ == "__main__":
    app.run()
