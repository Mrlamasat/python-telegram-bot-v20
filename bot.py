import os, psycopg2, logging, re, asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- الإعدادات (تأكد من ضبطها في Railway) ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591 
SOURCE_CHANNEL = -1003547072209 

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- إدارة قاعدة البيانات ---
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
        logging.error(f"❌ خطأ قاعدة البيانات: {e}")
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

# --- أدوات الاستخراج والتنظيف ---
def extract_info(text):
    if not text: return "مسلسل", 0
    # تنظيف النص من معلومات الجودة قبل الاستخراج
    clean_text = re.sub(r'(الجودة|المدة|✨|⏱|HD|📥|💿|⏳|🎞|دقيقة).*', '', text, flags=re.I).strip()
    
    ep_match = re.search(r'(?:الحلقة|حلقة|#|EP)\s*(\d+)', text, re.I)
    ep = int(ep_match.group(1)) if ep_match else 0
    if ep == 0:
        nums = re.findall(r'\b(\d+)\b', text)
        if nums: ep = int(nums[-1])
        
    title = re.sub(r'(?:الحلقة|حلقة|#|EP)\s*\d+.*', '', clean_text, flags=re.I).strip(" :-|")
    return title or "مسلسل", ep

# --- الأوامر الأساسية ---

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        v_id = str(message.command[1])
        res = db_query("SELECT title, ep_num, poster_id FROM videos WHERE v_id = %s", (v_id,))
        
        if res:
            title, ep, p_id = res[0]
            caption = f"<b>📺 {title}</b>\n<b>🎞 الحلقة: {ep}</b>"
            
            # إرسال البوستر إذا وجد
            if p_id:
                try: await client.send_photo(message.chat.id, p_id, caption=caption)
                except: pass
            
            # إرسال الفيديو الأصلي
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id))
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
        else:
            await message.reply_text("❌ هذه الحلقة غير مؤرشفة حالياً.")
    else:
        await message.reply_text(f"مرحباً بك يا محمد! البوت يحتوي حالياً على حلقات مؤرشفة وجاهزة.")

# --- أوامر الإدارة والأرشفة ---

@app.on_message(filters.command("fix_old_data") & filters.private)
async def fix_old_data_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    if len(message.command) < 3:
        return await message.reply_text("⚠️ استخدم: `/fix_old_data 1 3025`")

    start_id, end_id = int(message.command[1]), int(message.command[2])
    status_msg = await message.reply_text("🚀 جاري الأرشفة الشاملة...")
    
    count = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            msg = await client.get_messages(SOURCE_CHANNEL, msg_id)
            if not msg or msg.empty: continue
            
            if msg.video or msg.document or msg.animation:
                v_title, v_ep = extract_info(msg.caption)
                poster_id = None
                
                # البحث في الرسائل الـ 3 التالية (للبوستر أو الرقم)
                for next_id in range(msg_id + 1, msg_id + 4):
                    try:
                        n_msg = await client.get_messages(SOURCE_CHANNEL, next_id)
                        if n_msg.photo:
                            poster_id = n_msg.photo.file_id
                            break
                        elif n_msg.text:
                            _, t_ep = extract_info(n_msg.text)
                            if v_ep == 0: v_ep = t_ep
                    except: continue

                db_query("""
                    INSERT INTO videos (v_id, title, ep_num, poster_id, raw_caption)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (v_id) DO UPDATE SET ep_num=EXCLUDED.ep_num, poster_id=EXCLUDED.poster_id
                """, (str(msg_id), v_title, v_ep, poster_id, msg.caption or ""), fetch=False)
                count += 1
            
            if msg_id % 50 == 0:
                await status_msg.edit_text(f"⏳ معالجة... وصلنا لـ {msg_id}\nالمؤرشف: {count}")
                await asyncio.sleep(1)
        except: continue

    await status_msg.edit_text(f"✅ اكتملت المهمة! مؤرشف: {count}")

@app.on_message(filters.command("clean_titles") & filters.private)
async def clean_titles_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    m = await message.reply_text("🧼 جاري تنظيف العناوين من نصوص الجودة والوقت...")
    
    rows = db_query("SELECT v_id, title FROM videos")
    updated = 0
    for v_id, title in rows:
        # حذف نصوص الجودة والوقت والرموز
        new_title = re.sub(r'(الجودة|المدة|✨|⏱|HD|📥|💿|⏳|🎞|دقيقة).*', '', title, flags=re.I).strip(" :-|")
        if new_title != title:
            db_query("UPDATE videos SET title = %s WHERE v_id = %s", (new_title, v_id), fetch=False)
            updated += 1
    await m.edit_text(f"✅ تم تنظيف {updated} عنوان بنجاح!")

@app.on_message(filters.command("setep") & filters.private)
async def set_ep(client, message):
    if message.from_user.id != ADMIN_ID: return
    if len(message.command) < 3: return
    db_query("UPDATE videos SET ep_num = %s WHERE v_id = %s", (message.command[2], message.command[1]), fetch=False)
    await message.reply_text("✅ تم التعديل.")

if __name__ == "__main__":
    init_db()
    print("✅ البوت يعمل الآن...")
    app.run()
