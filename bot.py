import os, logging, re, asyncio
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# --- الإعدادات ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_ID = 7720165591
SOURCE_CHANNEL = -1003547072209

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_pool = pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")

def db_query(query, params=(), fetch=True):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch: return cur.fetchall()
        conn.commit()
    finally: db_pool.putconn(conn)

@app.on_message(filters.command("reset_db") & filters.user(ADMIN_ID))
async def reset_db_cmd(client, message):
    db_query("DROP TABLE IF EXISTS videos", fetch=False)
    db_query("""CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, title TEXT, poster_id TEXT, ep_num INTEGER DEFAULT 0, status TEXT DEFAULT 'posted'
        )""", fetch=False)
    await message.reply_text("🗑️ تم تصفير القاعدة بنجاح!")

@app.on_message(filters.command("sync_all") & filters.user(ADMIN_ID))
async def sync_all_old(client, message):
    if len(message.command) < 3: return await message.reply("`/sync_all 1 3025`")
    
    start_id = int(message.command[1])
    end_id = int(message.command[2])
    m = await message.reply("🚀 جاري الأرشفة... (تم تقليل السجلات لتفادي التعليق)")
    
    count = 0
    # جلب الرسائل على دفعات (أفضل للأداء)
    for i in range(start_id, end_id + 1, 100):
        ids = list(range(i, min(i + 100, end_id + 1)))
        try:
            messages = await client.get_messages(SOURCE_CHANNEL, ids)
            for j, msg in enumerate(messages):
                if msg and (msg.video or msg.document):
                    v_id = str(msg.id)
                    title, poster_id, ep_num = "غير مسمى", None, 0
                    
                    # فحص الرسائل التالية (الصورة والرقم)
                    try:
                        # جلب 5 رسائل تالية للتأكد من وجود البوستر والرقم
                        next_msgs = await client.get_messages(SOURCE_CHANNEL, list(range(msg.id + 1, msg.id + 4)))
                        for n_m in next_msgs:
                            if n_m.photo:
                                poster_id = n_m.photo.file_id
                                if n_m.caption: title = n_m.caption.strip()
                            elif n_m.text and ep_num == 0:
                                nums = re.findall(r'\d+', n_m.text)
                                if nums: ep_num = int(nums[0])
                    except: pass

                    db_query("""INSERT INTO videos (v_id, title, poster_id, ep_num, status) 
                                VALUES (%s, %s, %s, %s, 'posted')
                                ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num""",
                             (v_id, title, poster_id, ep_num), fetch=False)
                    count += 1
            
            await m.edit(f"⏳ معالجة: {i}\n✅ تم أرشفة: {count}")
            await asyncio.sleep(2) # تأخير بسيط لتفادي Rate limit تليجرام
            
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logging.error(f"Error: {e}")
            continue

    await m.edit(f"✅ انتهى! مؤرشف: {count}")

if __name__ == "__main__":
    app.run()
