import os, psycopg2, logging, re, asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# الإعدادات
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591 
SOURCE_CHANNEL = -1003547072209

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
    # البحث عن رقم الحلقة في أي نص (موجه أو كابشن)
    ep_match = re.search(r'(?:الحلقة|حلقة|#|EP)\s*(\d+)', text, re.I)
    ep = int(ep_match.group(1)) if ep_match else 0
    # إذا لم يجد كلمة "حلقة"، يبحث عن أي رقم منفرد
    if ep == 0:
        nums = re.findall(r'\b(\d+)\b', text)
        if nums: ep = int(nums[-1])
    
    title = re.sub(r'(?:الحلقة|حلقة|#|EP)\s*\d+.*', '', text, flags=re.I).strip()
    return title or "مسلسل", ep

@app.on_message(filters.command("fix_old_data") & filters.private)
async def fix_old_data_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    m = await message.reply_text("⏳ جاري تحليل الرسائل الموجهة وربط الحلقات تلقائياً...")
    
    count = 0
    all_msgs = []
    
    # 1. جلب تاريخ الشات بينك وبين البوت (الرسائل التي وجهتها)
    async for msg in client.get_chat_history(message.chat.id, limit=3000):
        if msg.forward_from_chat and msg.forward_from_chat.id == SOURCE_CHANNEL:
            all_msgs.append(msg)
    
    # عكس القائمة لتبدأ من الأقدم إلى الأحدث (كما في القناة)
    all_msgs.reverse()

    # 2. معالجة الرسائل بنظام الربط الذكي
    i = 0
    while i < len(all_msgs):
        msg = all_msgs[i]
        
        # إذا وجدنا فيديو، نبدأ بالبحث عن ملحقاته (رقم، بوستر) في الرسائل التالية له
        if msg.video or msg.document or msg.animation:
            v_id = str(msg.forward_from_message_id)
            v_title, v_ep = extract_info(msg.caption)
            poster_id = None
            
            # فحص الـ 5 رسائل التالية للفيديو بحثاً عن الرقم أو البوستر
            for j in range(1, 6):
                if (i + j) < len(all_msgs):
                    next_msg = all_msgs[i + j]
                    
                    # إذا كانت صورة، نعتبرها بوستر
                    if next_msg.photo:
                        poster_id = next_msg.photo.file_id
                        p_title, p_ep = extract_info(next_msg.caption)
                        if v_ep == 0: v_ep = p_ep
                        if v_title == "مسلسل": v_title = p_title
                    
                    # إذا كانت رسالة نصية (التي تحتوي على الرقم بعد اختيار الجودة)
                    elif next_msg.text:
                        _, t_ep = extract_info(next_msg.text)
                        if v_ep == 0: v_ep = t_ep
            
            # حفظ في قاعدة البيانات
            db_query("""
                INSERT INTO videos (v_id, title, ep_num, poster_id, raw_caption)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (v_id) DO UPDATE SET 
                ep_num=EXCLUDED.ep_num, poster_id=EXCLUDED.poster_id, title=EXCLUDED.title
            """, (v_id, v_title, v_ep, poster_id, msg.caption), fetch=False)
            count += 1
        
        i += 1

    await m.edit_text(f"✅ تم الانتهاء!\n📹 تمت أرشفة وتصحيح {count} حلقة بنجاح.")

if __name__ == "__main__":
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            video_quality TEXT DEFAULT 'HD',
            duration TEXT DEFAULT '00:00:00',
            poster_id TEXT,
            raw_caption TEXT,
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    app.run()
