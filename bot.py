import os
import psycopg2
import logging
import re
import difflib
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ForceReply
from pyrogram.enums import ParseMode

# ===== 1. الإعدادات الأساسية =====
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

# ===== 2. قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch: result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close(); conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# ===== 3. أدوات المعالجة =====
def convert_ar_no(text):
    if not text: return ""
    return text.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))

def normalize_text(text):
    if not text: return ""
    text = convert_ar_no(text).strip().lower()
    text = re.sub(r'^(مسلسل|فيلم|انمي|حلقة|الحلقة)\s*', '', text)
    text = re.sub(r'[أإآ]', 'ا', text).replace('ة', 'ه').replace('ى', 'ي')
    return re.sub(r'[^a-zا-ي0-9]', '', text)

def obfuscate_visual(text):
    return " . ".join(list(text)) if text else ""

def extract_info(caption):
    if not caption: return "مسلسل غير معروف", "1"
    ep_match = re.search(r'(\d+)', convert_ar_no(caption))
    ep_num = ep_match.group(1) if ep_match else "1"
    title = re.sub(r'(الحلقة|حلقة)?\s*\d+', '', caption).strip()
    return title, ep_num

async def get_episodes_markup(title, current_v_id):
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC", (title,))
    if not res: return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps: continue
        seen_eps.add(ep_num)
        label = f"✅ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}"))
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔍 بحث آخر", callback_data="start_search")])
    return buttons

# ===== 4. معالج الأوامر (الأولوية القصوى) =====
@app.on_message(filters.command(["start", "clear", "del", "stats"]))
async def commands_handler(client, message):
    cmd = message.command[0]

    if cmd == "clear":
        db_query("DELETE FROM videos WHERE status != 'posted'", fetch=False)
        return await message.reply_text("✅ تم تنظيف عمليات الرفع العالقة.")

    if cmd == "del" and message.from_user.id == ADMIN_ID:
        if len(message.command) < 3: return await message.reply_text("📝 `/del اسم رقم`")
        db_query("DELETE FROM videos WHERE title=%s AND ep_num=%s", (message.command[1], message.command[2]), fetch=False)
        return await message.reply_text("🗑️ تم الحذف.")

    if cmd == "start":
        if len(message.command) < 2:
            return await message.reply_text("مرحباً بك في بوت المسلسلات!", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔍 كيف أبحث؟")]], resize_keyboard=True))
        
        v_id = message.command[1]
        try:
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if not source_msg or source_msg.empty or not (source_msg.video or source_msg.document):
                return await message.reply_text("❌ الملف غير موجود أو فارغ في المصدر.")
            
            title, ep = extract_info(source_msg.caption)
            db_query("""INSERT INTO videos (v_id, title, ep_num, status, views) VALUES (%s, %s, %s, 'posted', 1)
                        ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, views=videos.views+1""", 
                     (v_id, title, ep), fetch=False)
        except Exception as e:
            res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
            if not res: return await message.reply_text(f"❌ خطأ: {e}")
            title, ep = res[0]

        # فحص الاشتراك
        try:
            member = await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
            if member.status in ["left", "kicked"] and message.from_user.id != ADMIN_ID:
                return await message.reply_text("⚠️ اشترك أولاً لمشاهدة الحلقة.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 انضمام", url=FORCE_SUB_LINK)]]))
        except: pass
        
        btns = await get_episodes_markup(title, v_id)
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), 
                                 caption=f"<b>📺 {obfuscate_visual(title)}</b>\n<b>🎞️ حلقة رقم: {ep}</b>", 
                                 reply_markup=InlineKeyboardMarkup(btns))

# ===== 5. معالج البحث (تم تعديل الفلتر ليتجاهل الأوامر) =====
@app.on_message(filters.private & filters.text & ~filters.command(["start", "clear", "del", "stats"]))
async def search_handler(client, message):
    # حماية إضافية: إذا بدأ النص بـ / ننهي الدالة فوراً
    if message.text.startswith("/"): return 
    
    query = normalize_text(message.text)
    if not query: return
    
    all_titles = [r[0] for r in db_query("SELECT DISTINCT title FROM videos WHERE status='posted'") or []]
    matches = [t for t in all_titles if query in normalize_text(t)]

    if matches:
        title = matches[0]
        res = db_query("SELECT v_id FROM videos WHERE title=%s ORDER BY CAST(ep_num AS INTEGER) ASC LIMIT 1", (title,))
        bot = await client.get_me()
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"🎬 عرض {title}", url=f"https://t.me/{bot.username}?start={res[0][0] or ''}")]])
        await message.reply_text(f"🔍 وجدنا: {title}", reply_markup=markup)
    else:
        await message.reply_text("❌ لم يتم العثور على نتائج. تأكد من كتابة الاسم صحيحاً.")

# ===== 6. نظام الاستلام من المصدر =====
@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document))
async def auto_receive(client, message):
    v_id = str(message.id)
    db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO NOTHING", (v_id,), fetch=False)
    await message.reply_text(f"✅ تم استلام الفيديو آيدي: {v_id}")

if __name__ == "__main__":
    app.run()
