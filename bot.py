import os, re, psycopg2, logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعداد السجلات لمراقبة أداء البوت في Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== [1] الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# المعرفات الخاصة بقنواتك (بصيغة int)
SOURCE_CHANNEL = int(-1003547072209)      
PUBLIC_POST_CHANNEL = int(-1003554018307)  
ADMIN_ID = int(7720165591)
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("railway_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] إدارة قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close(); conn.close()
        return res
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return []

# إنشاء الجدول لضمان استقرار التشغيل وتخزين البيانات
db_query("""
    CREATE TABLE IF NOT EXISTS videos (
        v_id TEXT PRIMARY KEY,
        title TEXT,
        ep_num INTEGER DEFAULT 0,
        poster_id TEXT,
        status TEXT DEFAULT 'waiting_poster'
    )
""", fetch=False)

# ===== [3] عرض الحلقة وترتيب الأزرار (للأعضاء) =====
async def show_episode(client, message, v_id, edit=False):
    v_id_str = str(v_id)
    # جلب البيانات من قاعدة البيانات
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id_str,))
    
    if not res:
        # إذا كانت حلقة قديمة، نحاول جلب العنوان من قناة المصدر
        try:
            msg = await client.get_messages(SOURCE_CHANNEL, int(v_id_str))
            title = msg.caption.split('\n')[0] if msg.caption else "حلقة غير معرفة"
            title = re.sub(r"\s+\.\s+", "", title).replace(".", "").strip() # تنظيف الاسم
            ep_num = 0
            db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted')", (v_id_str, title, ep_num), fetch=False)
        except:
            title, ep_num = "حلقة غير معرفة", 0
    else:
        title, ep_num = res[0]

    # جلب جميع حلقات المسلسل لترتيب الأزرار (1, 2, 3...)
    all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    
    buttons = []
    row = []
    for e_num, e_vid in all_eps:
        # إذا كان رقم الحلقة 0، نظهر معرف الفيديو مؤقتاً لحين إصلاحه بـ /set
        display_num = str(e_num) if e_num != 0 else f"?({e_vid})"
        btn_text = f"• {display_num} •" if str(e_vid) == v_id_str else display_num
        row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{e_vid}"))
        if len(row) == 5:
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    caption = f"📺 <b>{title}</b>\n🎬 <b>الحلقة رقم: {ep_num if ep_num != 0 else 'غير محددة'}</b>"
    chat_id = message.message.chat.id if hasattr(message, "data") else message.chat.id
    
    try:
        if edit and hasattr(message, "data"): await message.message.delete()
        await client.copy_message(chat_id, SOURCE_CHANNEL, int(v_id_str), caption=caption, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Copy Error: {e}")

# ===== [4] سيناريو المصدر (فيديو -> بوستر -> رقم الحلقة) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source_flow(client, message):
    try:
        # 1. استلام الفيديو
        if message.video or message.document:
            raw_title = message.caption.strip() if message.caption else "غير مسمى"
            title = re.sub(r"\s+\.\s+", "", raw_title).replace(".", "").strip()
            db_query("INSERT INTO videos (v_id, title, status) VALUES (%s, %s, 'waiting_poster') ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title", (str(message.id), title), fetch=False)
            await message.reply_text(f"✅ تم استلام فيديو: {title}\n(ID: {message.id})\nالآن أرسل البوستر.")

        # 2. استلام البوستر
        elif message.photo:
            res = db_query("SELECT v_id FROM videos WHERE status = 'waiting_poster' ORDER BY v_id DESC LIMIT 1")
            if res:
                v_id = res[0][0]
                db_query("UPDATE videos SET poster_id = %s, status = 'waiting_ep' WHERE v_id = %s", (message.photo.file_id, v_id), fetch=False)
                await message.reply_text(f"🖼️ تم حفظ البوستر لـ {v_id}\nأرسل رقم الحلقة الآن.")

        # 3. استلام الرقم والنشر النهائي
        elif message.text and message.text.isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status = 'waiting_ep' ORDER BY v_id DESC LIMIT 1")
            if res:
                v_id, title, p_id = res[0]
                ep = int(message.text)
                db_query("UPDATE videos SET ep_num = %s, status = 'posted' WHERE v_id = %s", (ep, v_id), fetch=False)
                
                me = await client.get_me()
                link = f"https://t.me/{me.username}?start={v_id}"
                
                # النشر في قناة المنشورات العامة
                await client.send_photo(
                    PUBLIC_POST_CHANNEL, 
                    p_id, 
                    caption=f"🎬 <b>{title}</b>\n📌 <b>الحلقة: {ep}</b>\n\n▶️ {link}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الآن", url=link)]])
                )
                await message.reply_text(f"🚀 تم النشر بنجاح: {title} - حلقة {ep}")
    except Exception as e:
        logger.error(f"Source Flow Error: {e}")

# ===== [5] التحكم والأوامر =====
@app.on_callback_query(filters.regex(r"^go_"))
async def navigation_handler(c, q):
    await show_episode(c, q, q.data.split("_")[1], edit=True)
    await q.answer()

@app.on_message(filters.command("start") & filters.private)
async def start_handler(c, m):
    if len(m.command) > 1: await show_episode(c, m, m.command[1])
    else: await m.reply_text(f"أهلاً بك يا محمد ({m.from_user.first_name})، النظام يعمل الآن بمحاذاة اليمين.")

@app.on_message(filters.command("set") & filters.user(ADMIN_ID))
async def manual_fix(c, m):
    """لإصلاح الحلقات القديمة: /set [ID] [الرقم] [الاسم]"""
    try:
        args = m.text.split(maxsplit=3)
        v_id, ep, title = args[1], args[2], args[3]
        title = re.sub(r"\s+\.\s+", "", title).replace(".", "").strip()
        db_query("UPDATE videos SET ep_num=%s, title=%s, status='posted' WHERE v_id=%s", (ep, title, v_id), fetch=False)
        db_query("INSERT INTO videos (v_id, title, ep_num, status) SELECT %s, %s, %s, 'posted' WHERE NOT EXISTS (SELECT 1 FROM videos WHERE v_id=%s)", (v_id, title, ep, v_id), fetch=False)
        await m.reply_text(f"✅ تم التحديث: {title} - حلقة {ep}")
    except:
        await m.reply_text("❌ الصيغة: `/set ID الرقم الاسم`")

if __name__ == "__main__":
    app.run()
