import os, logging, re, asyncio
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError

# إعدادات السجلات (Logs)
logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_ID = 7720165591
SOURCE_CHANNEL = -1003547072209

# التحقق من البيانات
if not BOT_TOKEN or API_ID == 0:
    logging.error("❌ خطأ: تأكد من إضافة BOT_TOKEN و API_ID في Railway Variables")
    exit(1)

# تعريف البوت بجلسة جديدة
app = Client("almohsen_final_v4", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات =====
try:
    db_pool = pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode="require")
except Exception as e:
    logging.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")

def db_query(query, params=(), fetch=True):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch: return cur.fetchall()
        conn.commit()
    except Exception as e:
        logging.error(f"❌ DB Query Error: {e}")
        conn.rollback()
    finally:
        db_pool.putconn(conn)

def init_db():
    db_query("""CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY, 
            title TEXT, 
            poster_id TEXT, 
            ep_num INTEGER DEFAULT 0, 
            status TEXT DEFAULT 'posted'
        )""", fetch=False)

# ===== أوامر المشرف (محمد) =====

@app.on_message(filters.command("reset_db") & filters.user(ADMIN_ID))
async def reset_db_cmd(client, message):
    db_query("DROP TABLE IF EXISTS videos", fetch=False)
    init_db()
    await message.reply_text("🗑️ تم تصفير قاعدة البيانات بنجاح يا محمد. جاهز للأرشفة الجديدة!")

@app.on_message(filters.command("sync_all") & filters.user(ADMIN_ID))
async def sync_all_cmd(client, message):
    if len(message.command) < 3:
        return await message.reply("⚠️ استخدم: `/sync_all 1 3025`")
    
    start_id, end_id = int(message.command[1]), int(message.command[2])
    m = await message.reply("🚀 انطلقت الأرشفة... يتم سحب (الفيديو -> الصورة -> الرقم)")
    
    count = 0
    # المعالجة دفعة واحدة لتقليل طلبات تليجرام وسجلات ريلواي
    for i in range(start_id, end_id + 1):
        try:
            # جلب رسالة الفيديو
            msg = await app.get_messages(SOURCE_CHANNEL, i)
            if msg and (msg.video or msg.document):
                v_id = str(msg.id)
                title, poster_id, ep_num = "غير مسمى", None, 0
                
                # جلب الـ 3 رسائل التالية (البوستر والرقم)
                next_ids = [msg.id + 1, msg.id + 2, msg.id + 3]
                next_msgs = await app.get_messages(SOURCE_CHANNEL, next_ids)
                
                for n_m in next_msgs:
                    if n_m.photo:
                        poster_id = n_m.photo.file_id
                        if n_m.caption: title = n_m.caption.strip()
                    elif n_m.text and ep_num == 0:
                        nums = re.findall(r'\d+', n_m.text)
                        if nums: ep_num = int(nums[0])

                # حفظ في PostgreSQL
                db_query("""INSERT INTO videos (v_id, title, poster_id, ep_num, status) 
                            VALUES (%s, %s, %s, %s, 'posted')
                            ON CONFLICT (v_id) DO UPDATE SET 
                            title=EXCLUDED.title, poster_id=EXCLUDED.poster_id, ep_num=EXCLUDED.ep_num""",
                         (v_id, title, poster_id, ep_num), fetch=False)
                count += 1
                
                if count % 20 == 0:
                    await m.edit(f"⏳ معالجة الرسالة: {i}\n✅ مؤرشف بنجاح: {count}\n🎬 آخر مسلسل: {title}")
            
            await asyncio.sleep(0.3) # سرعة متوازنة

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except RPCError as e:
            logging.error(f"❌ خطأ تليجرام عند {i}: {e.MESSAGE}")
            continue
        except Exception as e:
            logging.error(f"❌ خطأ غير متوقع: {e}")
            continue

    await m.edit(f"✅ مبروك يا محمد! اكتملت الأرشفة.\n📦 إجمالي الحلقات المرفوعة: {count}")

# ===== نظام التشغيل (Start) =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
        if res:
            t, e = res[0]
            await client.copy_message(
                message.chat.id, 
                SOURCE_CHANNEL, 
                int(v_id), 
                caption=f"🎬 **المسلسل:** {t}\n🎞️ **الحلقة:** {e}\n\n🍿 مشاهدة ممتعة!"
            )
        else:
            await message.reply("⚠️ عذراً يا محمد، هذه الحلقة غير مؤرشفة في قاعدة البيانات.")
    else:
        await message.reply(f"أهلاً بك يا {message.from_user.first_name} 👋\nالبوت شغال وجاهز لخدمتك.")

if __name__ == "__main__":
    init_db()
    app.run()
