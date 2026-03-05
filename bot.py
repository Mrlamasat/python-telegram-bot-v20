import os, logging, re, asyncio
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# إعداد السجلات الأساسية
logging.basicConfig(level=logging.INFO)

# جلب الإعدادات من البيئة
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_ID = 7720165591
SOURCE_CHANNEL = -1003547072209

# التحقق من البيانات قبل التشغيل
if not BOT_TOKEN or API_ID == 0:
    logging.error("❌ خطأ: البيانات ناقصة في Variables الاستضافة!")
    exit(1)

# تعريف البوت باسم جلسة جديد لتفادي أخطاء sign_in
app = Client("almohsen_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# إدارة قاعدة البيانات بذكاء
try:
    db_pool = pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode="require")
except Exception as e:
    logging.error(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

def db_query(query, params=(), fetch=True):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch: return cur.fetchall()
        conn.commit()
    finally: db_pool.putconn(conn)

# --- أوامر الإدارة ---

@app.on_message(filters.command("reset_db") & filters.user(ADMIN_ID))
async def reset_db(client, message):
    db_query("DROP TABLE IF EXISTS videos", fetch=False)
    db_query("""CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, title TEXT, poster_id TEXT, ep_num INTEGER DEFAULT 0, status TEXT DEFAULT 'posted'
        )""", fetch=False)
    await message.reply_text("🗑️ تم مسح القاعدة وتجهيزها من جديد يا محمد.")

@app.on_message(filters.command("sync_all") & filters.user(ADMIN_ID))
async def sync_all(client, message):
    if len(message.command) < 3: return await message.reply("أرسل: `/sync_all 1 3025`")
    
    start_id, end_id = int(message.command[1]), int(message.command[2])
    m = await message.reply("🚀 انطلقت الأرشفة.. جاري جلب الأسماء من وصف الصور..")
    
    count = 0
    # معالجة الرسائل على دفعات لسرعة الأداء وتقليل الـ Logs
    for i in range(start_id, end_id + 1, 50):
        ids = list(range(i, min(i + 50, end_id + 1)))
        try:
            msgs = await client.get_messages(SOURCE_CHANNEL, ids)
            for msg in msgs:
                if msg and (msg.video or msg.document):
                    v_id = str(msg.id)
                    title, p_id, ep = "غير مسمى", None, 0
                    
                    # فحص الرسائل التالية (الصورة والرقم)
                    next_batch = await client.get_messages(SOURCE_CHANNEL, [msg.id + 1, msg.id + 2])
                    if next_batch[0].photo:
                        p_id = next_batch[0].photo.file_id
                        title = next_batch[0].caption.strip() if next_batch[0].caption else "بدون عنوان"
                    if next_batch[1].text:
                        nums = re.findall(r'\d+', next_batch[1].text)
                        if nums: ep = int(nums[0])

                    db_query("""INSERT INTO videos (v_id, title, poster_id, ep_num, status) 
                                VALUES (%s, %s, %s, %s, 'posted')
                                ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num""",
                             (v_id, title, p_id, ep), fetch=False)
                    count += 1
            
            await m.edit(f"⏳ معالجة الرسالة {i}\n✅ مؤرشف: {count}")
            await asyncio.sleep(2)
        except FloodWait as e: await asyncio.sleep(e.value)
        except Exception: continue

    await m.edit(f"✅ مبروك يا محمد! اكتملت الأرشفة لـ {count} حلقة.")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
        if res:
            t, e = res[0]
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"🎬 {t}\n🎞️ حلقة: {e}")
    else:
        await message.reply("البوت شغال وجاهز!")

if __name__ == "__main__":
    app.run()
