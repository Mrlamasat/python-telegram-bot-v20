import os, psycopg2, logging, re, asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# الإعدادات
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591 
SOURCE_CHANNEL = -1003547072209 # قناة المصدر الخاصة بك

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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
        logging.error(f"❌ DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

def extract_info(text):
    if not text: return "مسلسل", 0
    ep_match = re.search(r'(?:الحلقة|حلقة|#|EP)\s*(\d+)', text, re.I)
    ep = int(ep_match.group(1)) if ep_match else 0
    if ep == 0:
        nums = re.findall(r'\b(\d+)\b', text)
        if nums: ep = int(nums[-1])
    title = re.sub(r'(?:الحلقة|حلقة|#|EP)\s*\d+.*', '', text, flags=re.I).strip()
    return title or "مسلسل", ep

@app.on_message(filters.command("fix_old_data") & filters.private)
async def fix_old_data_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    # نطلب من الأدمن تحديد البداية والنهاية
    if len(message.command) < 3:
        return await message.reply_text("⚠️ **أرسل الأمر مع نطاق الرسائل:**\n`/fix_old_data 1 5000`\n(حيث 1 هو البداية و5000 هو رقم آخر رسالة في القناة)")

    start_id = int(message.command[1])
    end_id = int(message.command[2])
    
    status_msg = await message.reply_text(f"🚀 بدأت عملية الأرشفة الشاملة من {start_id} إلى {end_id}...")
    
    count = 0
    # فحص الرسائل بناءً على الـ ID (تجاوز لقيود History)
    for msg_id in range(start_id, end_id + 1):
        try:
            # جلب الرسالة مباشرة برقمها
            msg = await client.get_messages(SOURCE_CHANNEL, msg_id)
            if not msg or msg.empty: continue
            
            if msg.video or msg.document or msg.animation:
                v_title, v_ep = extract_info(msg.caption)
                poster_id = None
                
                # البحث الذكي فيما يلي الفيديو (الرسائل 5 التالية)
                for next_id in range(msg_id + 1, msg_id + 6):
                    try:
                        n_msg = await client.get_messages(SOURCE_CHANNEL, next_id)
                        if not n_msg or n_msg.empty: continue
                        
                        if n_msg.photo:
                            poster_id = n_msg.photo.file_id
                            p_title, p_ep = extract_info(n_msg.caption)
                            if v_ep == 0: v_ep = p_ep
                            if v_title == "مسلسل": v_title = p_title
                        elif n_msg.text:
                            _, t_ep = extract_info(n_msg.text)
                            if v_ep == 0: v_ep = t_ep
                    except: continue

                # حفظ في قاعدة البيانات
                db_query("""
                    INSERT INTO videos (v_id, title, ep_num, poster_id, raw_caption)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (v_id) DO UPDATE SET 
                    ep_num=EXCLUDED.ep_num, poster_id=EXCLUDED.poster_id, title=EXCLUDED.title
                """, (str(msg_id), v_title, v_ep, poster_id, msg.caption or ""), fetch=False)
                count += 1
            
            # تحديث الحالة كل 20 رسالة لكي لا يمل المستخدم وتجنباً لضغط تليجرام
            if msg_id % 20 == 0:
                await status_msg.edit_text(f"⏳ جاري الفحص...\nوصلنا للرسالة: {msg_id}\nتم أرشفة: {count} حلقة.")
                await asyncio.sleep(0.5)

        except Exception as e:
            logging.error(f"Error at {msg_id}: {e}")
            continue

    await status_msg.edit_text(f"✅ اكتملت المهمة بنجاح!\n📹 إجمالي ما تم أرشفته: {count}")

if __name__ == "__main__":
    app.run()
