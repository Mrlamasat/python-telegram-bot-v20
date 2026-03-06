import os
import psycopg2
import re
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية (تأكد من وجودها في ريلوي) =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
ADMIN_ID = 7464197368 

# اسم جلسة جديد تماماً لضمان عدم التعليق
app = Client("railway_final_stable", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ذاكرة مؤقتة لبيانات البوت
BOT_CACHE = {"username": None}

def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=10)
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"Database Error: {e}")
        return []

def obfuscate_visual(text):
    if not text: return "مسلسل"
    clean = re.sub(r'[^\w\s]', '', text).replace(" ", "")
    return " . ".join(list(clean))

async def get_bot_username():
    if not BOT_CACHE["username"]:
        me = await app.get_me()
        BOT_CACHE["username"] = me.username
    return BOT_CACHE["username"]

# --- نظام الإحصائيات ---
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def get_stats(client, message):
    res = db_query("SELECT title, SUM(views) FROM videos GROUP BY title ORDER BY SUM(views) DESC LIMIT 5")
    if not res:
        return await message.reply_text("❌ لا توجد بيانات حالياً.")
    
    text = "📊 <b>تقرير المشاهدات العام:</b>\n\n"
    for title, v in res:
        text += f"• {obfuscate_visual(title)} ← {v} مشاهدة\n"
    await message.reply_text(text, parse_mode=ParseMode.HTML)

# --- نظام الرفع (داخل قناة المصدر) ---
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    # إذا كان فيديو أو ملف
    if message.video or message.document:
        v_id = str(message.id)
        db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting') ON CONFLICT (v_id) DO UPDATE SET status='waiting'", (v_id,), fetch=False)
        await message.reply_text("✅ تم استلام الفيديو!\n📌 أرسل الآن (البوستر) مع اسم المسلسل في الوصف:")
    
    # رسالة تشخيصية: للتأكد أن البوت يرى القناة
    elif message.text and not message.text.isdigit():
        await message.reply_text(f"🚀 البوت متصل بالقناة ويسمعك!\nآيدي الدردشة: `{message.chat.id}`", parse_mode=ParseMode.MARKDOWN)

    # استقبال البوستر (صورة مع وصف)
    elif message.photo:
        res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if not res: return
        v_id = res[0][0]
        title = message.caption or "مسلسل رمضان"
        db_query("UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s", (title, message.photo.file_id, v_id), fetch=False)
        await message.reply_text(f"📌 تم حفظ البوستر لـ: {title}\n🔢 أرسل الآن رقم الحلقة فقط:")

    # استقبال رقم الحلقة
    elif message.text and message.text.isdigit():
        res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
        if not res: return
        
        v_id, title, p_id = res[0]
        ep_num = int(message.text)
        db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)
        
        # النشر التلقائي في القناة العامة
        username = await get_bot_username()
        pub_caption = f"🎬 <b>{obfuscate_visual(title)}</b>\n\n<b>الحلقة: [{ep_num}]</b>"
        pub_markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{username}?start={v_id}")]])
        
        await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=pub_caption, reply_markup=pub_markup)
        await message.reply_text(f"🚀 تم النشر بنجاح في القناة العامة!")

# --- نظام العرض (للمشتركين) ---
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("أهلاً بك يا محمد! ابدأ المشاهدة من قنواتنا.")

    v_id = message.command[1]
    
    # تحديث البيانات فوراً
    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1, last_view = CURRENT_TIMESTAMP WHERE v_id = %s", (v_id,), fetch=False)
    
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not res: return await message.reply_text("⚠️ الحلقة غير موجودة.")

    title, ep = res[0]
    username = await get_bot_username()
    
    # جلب قائمة الحلقات للأزرار
    ep_res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
    btns, row, seen = [], [], set()
    for vid, e_n in ep_res:
        if e_n == 0 or e_n in seen: continue
        seen.add(e_n)
        label = f"✅ {e_n}" if str(vid) == str(v_id) else f"{e_n}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{username}?start={vid}"))
        if len(row) == 5:
            btns.append(row); row = []
    if row: btns.append(row)

    caption = f"<b>📺 {obfuscate_visual(title)} - حلقة {ep}</b>"
    
    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=InlineKeyboardMarkup(btns))
    except Exception as e:
        await message.reply_text(f"⚠️ خطأ: {e}")

if __name__ == "__main__":
    app.run()
