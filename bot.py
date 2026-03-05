import os, logging, re, asyncio
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
        if fetch:
            return cur.fetchall()
        conn.commit()
    finally:
        db_pool.putconn(conn)

# --- 1. أمر مسح قاعدة البيانات بالكامل ---
@app.on_message(filters.command("reset_db") & filters.user(ADMIN_ID))
async def reset_db_cmd(client, message):
    db_query("DROP TABLE IF EXISTS videos", fetch=False)
    # إعادة إنشاء الجدول نظيفاً
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            ep_num INTEGER DEFAULT 0,
            status TEXT DEFAULT 'posted'
        )
    """, fetch=False)
    await message.reply_text("🗑️ تم مسح قاعدة البيانات بالكامل وإعادة تجهيزها بنجاح!")

# --- 2. أمر الأرشفة الذكية (الاعتماد على وصف الصورة والرقم التالي) ---
@app.on_message(filters.command("sync_all") & filters.user(ADMIN_ID))
async def sync_all_old(client, message):
    if len(message.command) < 3:
        return await message.reply("⚠️ أرسل: `/sync_all 1 3025`")
    
    start_id, end_id = int(message.command[1]), int(message.command[2])
    m = await message.reply("🚀 بدأت عملية الأرشفة الكبرى... جاري تحليل التسلسل (فيديو -> صورة -> رقم)")
    
    count = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            msg = await client.get_messages(SOURCE_CHANNEL, msg_id)
            # إذا وجدنا فيديو (بداية السلسلة)
            if msg and (msg.video or msg.document):
                v_id = str(msg.id)
                series_title = "غير مسمى"
                ep_num = 0
                poster_id = None
                
                # أ- البحث عن البوستر (الرسالة التالية مباشرة)
                poster_msg = await client.get_messages(SOURCE_CHANNEL, msg_id + 1)
                if poster_msg.photo:
                    poster_id = poster_msg.photo.file_id
                    if poster_msg.caption:
                        series_title = poster_msg.caption.strip() # الاسم من وصف الصورة
                
                # ب- البحث عن رقم الحلقة (الرسالة التي تلي البوستر)
                ep_msg = await client.get_messages(SOURCE_CHANNEL, msg_id + 2)
                if ep_msg.text:
                    nums = re.findall(r'\d+', ep_msg.text)
                    if nums:
                        ep_num = int(nums[0]) # أول رقم يجده بعد الصورة

                # ج- حفظ البيانات في القاعدة
                db_query("""
                    INSERT INTO videos (v_id, title, poster_id, ep_num, status) 
                    VALUES (%s, %s, %s, %s, 'posted')
                    ON CONFLICT (v_id) DO UPDATE SET 
                    title=EXCLUDED.title, poster_id=EXCLUDED.poster_id, ep_num=EXCLUDED.ep_num
                """, (v_id, series_title, poster_id, ep_num), fetch=False)
                count += 1

            if msg_id % 50 == 0:
                await m.edit(f"⏳ معالجة الرسالة: {msg_id}\n✅ مؤرشف بنجاح: {count}\n🎬 آخر مسلسل: {series_title}")
                await asyncio.sleep(1) # لتفادي الحظر من تليجرام
        except Exception as e:
            logging.error(f"Error at {msg_id}: {e}")
            continue
    
    await m.edit(f"✅ اكتملت الأرشفة!\nتم رفع {count} حلقة بنجاح بالاعتماد على وصف الصور والأرقام التالية لها.")

# --- نظام التشغيل للمشتركين ---
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
        if res:
            title, ep = res[0]
            cap = f"<b>📺 المسلسل: {title}</b>\n<b>🎞️ الحلقة: {ep}</b>\n\n🍿 مشاهدة ممتعة!"
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap)
    else:
        await message.reply("مرحباً بك يا محمد! استخدم `/reset_db` ثم `/sync_all` للأرشفة.")

if __name__ == "__main__":
    app.run()
