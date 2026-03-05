import os, psycopg2, logging, re, asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# --- الإعدادات ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591 
SOURCE_CHANNEL = -1003547072209 

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- قاعدة البيانات ---
def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else None
        conn.commit()
        return res
    except Exception as e:
        logging.error(f"❌ DB ERROR: {e}")
        return None
    finally:
        if conn: conn.close()

# --- مصفاة العناوين الذكية ---
def smart_clean_title(text):
    if not text: return "مفقود ⚠️"
    garbage_patterns = [r"الجودة.*", r"المدة.*", r"سنة العرض.*", r"مشاهدة ممتعة", r"✨", r"⏱", r"HD", r"📥"]
    temp = text
    for p in garbage_patterns: temp = re.sub(p, "", temp, flags=re.I)
    temp = re.sub(r'(?:الحلقة|حلقة|#|EP)\s*\d+.*', '', temp, flags=re.I)
    temp = re.sub(r'\d+', '', temp)
    temp = re.sub(r'[^\s\w\u0600-\u06FF]', '', temp)
    final = re.sub(r'\s+', ' ', temp).strip()
    return final if len(final) > 1 else "مفقود ⚠️"

# --- معالج تعديل العناوين ---
@app.on_message(filters.command("edit") & filters.private)
async def edit_request(client, message):
    if message.from_user.id != ADMIN_ID: return
    if len(message.command) < 2: return
    
    v_id = message.command[1]
    await message.reply_text(
        f"📝 أرسل الآن الاسم الجديد للفيديو رقم `{v_id}`:\n(قم بالرد على هذه الرسالة بالاسم الجديد)",
        reply_markup=ForceReply(selective=True)
    )

@app.on_message(filters.reply & filters.private)
async def process_edit(client, message):
    if message.from_user.id != ADMIN_ID: return
    if not message.reply_to_message.text: return
    
    # استخراج الـ ID من رسالة البوت السابقة
    v_id_search = re.search(r'رقم `(\d+)`', message.reply_to_message.text)
    if v_id_search:
        v_id = v_id_search.group(1)
        new_title = message.text.strip()
        
        db_query("UPDATE videos SET title = %s WHERE v_id = %s", (new_title, v_id), fetch=False)
        await message.reply_text(f"✅ تم تحديث العنوان بنجاح!\n🆔 المعرف: `{v_id}`\n🎬 الاسم الجديد: **{new_title}**")

# --- أمر التحقق من العناوين المفقودة ---
@app.on_message(filters.command("check_missing") & filters.private)
async def check_missing(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    rows = db_query("SELECT v_id, ep_num FROM videos WHERE title = 'مفقود ⚠️' OR title = 'مسلسل' LIMIT 10")
    if not rows:
        return await message.reply_text("✅ كل العناوين تبدو سليمة ومكتملة!")
    
    for v_id, ep in rows:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("تعديل الاسم ✏️", callback_data=f"edit_{v_id}")]])
        await message.reply_text(f"⚠️ فيديو بدون اسم!\n🆔 المعرف: `{v_id}`\n🎞 الحلقة: {ep}", reply_markup=btn)

@app.on_callback_query(filters.regex(r"^edit_"))
async def cb_edit(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    await callback_query.message.reply_text(
        f"📝 أرسل الاسم الجديد للمعرف `{v_id}`:",
        reply_markup=ForceReply(selective=True)
    )
    await callback_query.answer()

# --- أمر التنظيف العام ---
@app.on_message(filters.command("clean_titles") & filters.private)
async def clean_titles_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    m = await message.reply_text("🧼 تنظيف وتحليل...")
    rows = db_query("SELECT v_id, raw_caption FROM videos")
    for v_id, raw in rows:
        if raw:
            new_title = smart_clean_title(raw)
            db_query("UPDATE videos SET title = %s WHERE v_id = %s", (new_title, v_id), fetch=False)
    await m.edit_text("✅ انتهى التنظيف! استخدم `/check_missing` للتأكد من وجود نواقص.")

if __name__ == "__main__":
    app.run()
