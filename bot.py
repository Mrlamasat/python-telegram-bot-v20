import os, psycopg2, logging, re, asyncio, time
from datetime import datetime
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات وتعدد القنوات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209  # قناة المصدر
ADMIN_ID = 7720165591            # معرف محمد المحسن
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

# قائمة قنوات النشر الأربعة
PUBLIC_CHANNELS = [
    -1003554018307,
    -1003790915936,
    -1003678294148,
    -1003690441303
]

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] دالة قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close(); conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

# ===== [3] استخراج رقم الحلقة بذكاء =====
def extract_ep_num(text):
    if not text: return 0
    # يبحث بعد كلمات (حلقه، حلقة، الحلقة، رقم) أو داخل [ ]
    pattern = r"(?:حلقه|حلقة|الحلقة|الحلقه|رقم|الحلقہ)\s*[:\-\s!\[]*(\d+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match: return int(match.group(1))
    bracket_match = re.search(r"\[(\d+)\]", text)
    if bracket_match: return int(bracket_match.group(1))
    return 0

# ===== [4] أمر الإصلاح والربط الشامل (لجميع القنوات) =====
@app.on_message(filters.command("fix_all") & filters.user(ADMIN_ID))
async def fix_and_sync(client, message):
    msg = await message.reply_text("🔄 جاري فحص وإصلاح قنوات النشر الـ 4... يرجى الانتظار.")
    
    # حذف البيانات التالفة (أصفار أو عناوين فارغة)
    db_query("DELETE FROM videos WHERE ep_num <= 0 OR title = 'فيديو' OR title IS NULL", fetch=False)
    
    total_fixed = 0
    for channel_id in PUBLIC_CHANNELS:
        try:
            # التأكد من أن البوت عضو في القناة
            await client.get_chat(channel_id)
            
            async for post in client.get_chat_history(channel_id, limit=300):
                if post.reply_markup:
                    for row in post.reply_markup.inline_keyboard:
                        for btn in row:
                            if btn.url and "start=" in btn.url:
                                try:
                                    v_id = btn.url.split("start=")[1]
                                    source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                                    if source_msg and (source_msg.caption or source_msg.text):
                                        raw_text = source_msg.caption or source_msg.text
                                        title = raw_text.split('\n')[0][:50]
                                        ep = extract_ep_num(raw_text)
                                        if ep > 0:
                                            db_query("""
                                                INSERT INTO videos (v_id, title, ep_num, status) 
                                                VALUES (%s, %s, %s, 'posted')
                                                ON CONFLICT (v_id) DO UPDATE SET ep_num = EXCLUDED.ep_num, title = EXCLUDED.title
                                            """, (v_id, title, ep), fetch=False)
                                            total_fixed += 1
                                except: continue
        except Exception as e:
            logging.error(f"Error in channel {channel_id}: {e}")
            continue

    await msg.edit_text(f"✅ تم الانتهاء!\nتم ربط وتحديث {total_fixed} حلقة بنجاح من جميع القنوات.")

# ===== [5] عرض الحلقة للمستخدم =====
async def show_episode(client, message, v_id):
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    title, ep = (res[0][0], res[0][1]) if res else (None, 0)

    # إصلاح تلقائي سريع إذا لم تكن موجودة أو رقمها 0
    if not res or ep == 0:
        try:
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if source_msg and (source_msg.caption or source_msg.text):
                raw_text = source_msg.caption or source_msg.text
                title = raw_text.split('\n')[0][:50]
                ep = extract_ep_num(raw_text)
                if ep > 0:
                    db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET ep_num = EXCLUDED.ep_num, title = EXCLUDED.title", (v_id, title, ep), fetch=False)
        except: pass

    if not title: return await message.reply_text("❌ لم يتم العثور على بيانات الحلقة.")

    # جلب أزرار الحلقات (5 في السطر)
    other_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s AND status = 'posted' AND ep_num > 0 ORDER BY ep_num ASC", (title,))
    keyboard = []
    if other_eps:
        row = []
        me = await client.get_me()
        for o_ep, o_vid in other_eps:
            row.append(InlineKeyboardButton(f"{o_ep}", url=f"https://t.me/{me.username}?start={o_vid}"))
            if len(row) == 5:
                keyboard.append(row); row = []
        if row: keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])

    caption = f"<b>{title} - الحلقة {ep if ep > 0 else 'جاري التحديث'}</b>"
    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
        db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
    except: await message.reply_text("⚠️ فشل في إرسال الحلقة.")

# ===== [6] أوامر التشغيل والبداية =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text("👋 أهلاً بك في بوت المشاهدة.")

# ===== [7] دالة معالجة Flood Wait =====
async def handle_flood_wait(e):
    wait_time = e.value  # عدد الثواني المطلوب الانتظار
    logging.warning(f"⚠️ Flood wait required: {wait_time} seconds")
    print(f"⚠️ توقف مؤقت: الانتظار {wait_time} ثانية بسبب ضغط الطلبات...")
    await asyncio.sleep(wait_time)
    return True

# ===== [8] تشغيل البوت مع معالجة الأخطاء =====
def main():
    max_retries = 5
    retry_count = 0
    
    print("🚀 بدء تشغيل البوت...")
    
    while retry_count < max_retries:
        try:
            # حذف ملف الجلسة القديم إذا كان موجوداً
            session_file = "railway_final_pro.session"
            if os.path.exists(session_file):
                os.remove(session_file)
                print("✅ تم حذف ملف الجلسة القديم")
            
            print(f"📡 محاولة تشغيل البوت رقم {retry_count + 1}")
            
            # التحقق من وجود التوكن
            if not BOT_TOKEN:
                print("❌ خطأ: BOT_TOKEN غير موجود في متغيرات البيئة")
                return
            
            print(f"✅ API_ID: {API_ID}")
            print(f"✅ تم تحميل BOT_TOKEN بنجاح")
            
            # تشغيل البوت
            app.run()
            break
            
        except FloodWait as e:
            retry_count += 1
            wait_time = e.value
            print(f"⚠️ Flood Wait: الانتظار {wait_time} ثانية (محاولة {retry_count}/{max_retries})")
            
            # تنفيذ الانتظار بشكل غير متزامن
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(handle_flood_wait(e))
                loop.close()
            except:
                # إذا فشل الانتظار غير المتزامن، استخدم الانتظار المتزامن
                time.sleep(wait_time)
            
        except Exception as e:
            retry_count += 1
            print(f"❌ خطأ غير متوقع: {type(e).__name__}: {e}")
            
            if retry_count < max_retries:
                wait_time = 30 * retry_count  # زيادة وقت الانتظار مع كل محاولة
                print(f"⏳ الانتظار {wait_time} ثانية قبل إعادة المحاولة...")
                time.sleep(wait_time)
    
    if retry_count >= max_retries:
        print("❌ فشل تشغيل البوت بعد 5 محاولات")
        print("📝 الرجاء التحقق من:")
        print("1. صحة BOT_TOKEN في متغيرات البيئة")
        print("2. عدم وجود عدة نسخ من البوت تعمل")
        print("3. اتصال الإنترنت")
    else:
        print("✅ تم تشغيل البوت بنجاح!")

# ===== [9] نقطة الدخول الرئيسية =====
if __name__ == "__main__":
    main()
