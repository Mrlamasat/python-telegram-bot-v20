import os, psycopg2, logging, re
from datetime import datetime
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

# ===== [2] دالة استخراج الرقم المطورة جداً =====
def extract_ep_num(text):
    if not text: return 0
    # يبحث عن الرقم بعد الكلمة مهما كانت الرموز الفاصلة
    pattern = r"(?:حلقه|حلقة|الحلقة|الحلقه|رقم|الحلقہ)\s*[:\-\s!\[]*(\d+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # بحث عن الرقم داخل [ ]
    bracket_match = re.search(r"\[(\d+)\]", text)
    if bracket_match:
        return int(bracket_match.group(1))
    
    return 0

# ===== [3] عرض الحلقة =====
async def show_episode(client, message, v_id):
    # جلب البيانات
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    
    # إذا كانت الحلقة تظهر 0، نجبر البوت على إعادة القراءة من المصدر
    force_update = False
    if res and res[0][1] == 0:
        force_update = True

    if not res or force_update:
        try:
            source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if source_msg and (source_msg.caption or source_msg.text):
                raw_text = source_msg.caption or source_msg.text
                title = raw_text.split('\n')[0][:50]
                ep = extract_ep_num(raw_text)
                
                # تحديث البيانات في القاعدة لضمان الإصلاح الدائم
                db_query("""
                    INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted')
                    ON CONFLICT (v_id) DO UPDATE SET ep_num = EXCLUDED.ep_num, title = EXCLUDED.title
                """, (v_id, title, ep), fetch=False)
            else:
                title, ep = (res[0][0], 0) if res else ("فيديو", 0)
        except:
            if not res: return await message.reply_text("❌ لم يتم العثور على الحلقة.")
            title, ep = res[0]
    else:
        title, ep = res[0]

    try:
        caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>\n━━━━━━━━━━━━━━━"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 اشترك بالقناه الإحتياطيه", url=BACKUP_CHANNEL_LINK)]])
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)
        
        db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
        db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
    except Exception as e:
        await message.reply_text("⚠️ فشل إرسال الفيديو.")

# ===== [4] الأوامر والنشر =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    if message.video or message.document:
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT DO NOTHING", (str(message.id),), fetch=False)
        await message.reply_text(f"✅ تم استلام فيديو {message.id}")
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (message.caption, message.photo.file_id, res[0][0]), fetch=False)
            await message.reply_text(f"🖼️ تم حفظ البوستر")
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if res:
            v_id, title, p_id = res[0]; ep_num = int(message.text)
            db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
            me = await client.get_me()
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
            await client.send_photo(PUBLIC_POST_CHANNEL, p_id, f"🎬 <b>{title}</b>\n<b>الحلقة: [{ep_num}]</b>", reply_markup=markup)
            await message.reply_text(f"🚀 تم النشر!")

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text(f"👋 أهلاً بك يا محمد.")

if __name__ == "__main__":
    app.run()
