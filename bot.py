import os, psycopg2, logging, re, asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- إعدادات البيئة ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591 
SOURCE_CHANNEL = -1003547072209 

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- نظام قاعدة البيانات ---
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

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            poster_id TEXT,
            raw_caption TEXT,
            views INTEGER DEFAULT 0
        )
    """, fetch=False)

# --- دوائر التنظيف والاستخراج (تعديل الأرقام والرموز) ---
def clean_title_only(text):
    if not text: return "مسلسل"
    
    # 1. حذف نصوص الجودة والوقت
    garbage = [r"الجودة\s*[:：]?", r"المدة\s*[:：]?", r"دقيقة", r"HD", r"📥", r"💿", r"⏳", r"🎞"]
    for word in garbage:
        text = re.sub(word, "", text, flags=re.I)
    
    # 2. حذف كلمة (الحلقة/حلقة) وما يليها تماماً
    text = re.sub(r'(?:الحلقة|حلقة|#|EP).*', '', text, flags=re.I)
    
    # 3. حذف جميع الأرقام من العنوان
    text = re.sub(r'\d+', '', text)
    
    # 4. حذف الرموز التعبيرية (Emojis) والايقونات والزخارف
    # نبقي فقط على الحروف العربية والإنجليزية والمسافات
    text = re.sub(r'[^\s\w\u0600-\u06FF]', '', text)
    
    # 5. تنظيف المسافات الزائدة
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text if text else "مسلسل"

def extract_episode(text):
    if not text: return 0
    ep_match = re.search(r'(?:الحلقة|حلقة|#|EP)\s*(\d+)', text, re.I)
    if ep_match: return int(ep_match.group(1))
    nums = re.findall(r'\b(\d+)\b', text)
    return int(nums[-1]) if nums else 0

# --- أوامر البوت ---

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        v_id = str(message.command[1])
        res = db_query("SELECT title, ep_num, poster_id FROM videos WHERE v_id = %s", (v_id,))
        if res:
            title, ep, p_id = res[0]
            caption = f"<b>📺 {title}</b>\n<b>🎞 الحلقة: {ep}</b>"
            if p_id:
                try: await client.send_photo(message.chat.id, p_id, caption=caption)
                except: pass
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id))
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
        else:
            await message.reply_text("❌ الحلقة غير موجودة.")
    else:
        await message.reply_text("مرحباً بك يا محمد! البوت جاهز للعمل.")

@app.on_message(filters.command("fix_old_data") & filters.private)
async def fix_old_data_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    if len(message.command) < 3: return await message.reply_text("`/fix_old_data 1 3025`")
    
    start_id, end_id = int(message.command[1]), int(message.command[2])
    m = await message.reply_text("🚀 جاري الأرشفة والفلترة...")
    
    count = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            msg = await client.get_messages(SOURCE_CHANNEL, msg_id)
            if msg and (msg.video or msg.document or msg.animation):
                v_ep = extract_episode(msg.caption)
                v_title = clean_title_only(msg.caption)
                poster_id = None
                
                # البحث عن ملحقات
                for n_id in range(msg_id + 1, msg_id + 4):
                    try:
                        n_msg = await client.get_messages(SOURCE_CHANNEL, n_id)
                        if n_msg.photo: poster_id = n_msg.photo.file_id; break
                        elif n_msg.text and v_ep == 0: v_ep = extract_episode(n_msg.text)
                    except: continue

                db_query("""
                    INSERT INTO videos (v_id, title, ep_num, poster_id, raw_caption)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (v_id) DO UPDATE SET 
                    title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, poster_id=EXCLUDED.poster_id
                """, (str(msg_id), v_title, v_ep, poster_id, msg.caption or ""), fetch=False)
                count += 1
            if msg_id % 100 == 0: await m.edit_text(f"⏳ وصلنا لـ {msg_id}\n✅ أرشفنا: {count}")
        except: continue
    await m.edit_text(f"✅ انتهى! تم أرشفة وتصفية {count} حلقة.")

@app.on_message(filters.command("clean_titles") & filters.private)
async def clean_titles_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    m = await message.reply_text("🧼 جاري تنقية الأسماء من الأرقام والرموز...")
    rows = db_query("SELECT v_id, title, raw_caption FROM videos")
    updated = 0
    for v_id, title, raw in rows:
        # نستخدم raw_caption لإعادة استخراج الاسم بنظافة إذا كان العنوان القديم مشوهاً
        new_title = clean_title_only(raw if raw else title)
        if new_title != title:
            db_query("UPDATE videos SET title = %s WHERE v_id = %s", (new_title, v_id), fetch=False)
            updated += 1
    await m.edit_text(f"✅ تم تنقية {updated} عنوان بنجاح!")

if __name__ == "__main__":
    init_db()
    app.run()
