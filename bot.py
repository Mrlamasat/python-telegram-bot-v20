import os
import psycopg2
import logging
import re
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209 
ADMIN_ID = 7464197368 # آيدي حسابك

app = Client("mohammed_bot_final_v2", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        if conn: conn.close()
        return None

# ===== تنظيف الأسماء (نظام صارم جداً) =====
def clean_name_strict(text):
    if not text: return "مسلسل"
    # نأخذ السطر الأول فقط ونحذف أي أرقام أو رموز
    first_line = text.split('\n')[0].strip()
    clean = re.sub(r'\d+', '', first_line) # حذف الأرقام
    clean = re.sub(r'[^\w\s]', '', clean) # حذف الرموز
    # حذف الكلمات الشائعة التي تخرب الربط
    for word in ["الحلقة", "حلقة", "مشاهدة", "اضغط", "هنا", "جديدة"]:
        clean = clean.replace(word, "")
    return clean.replace(" ", "").strip()

def visual_name(text):
    """عرض الاسم بنقاط للجمالية"""
    name = clean_name_strict(text)
    return " . ".join(list(name))

# ===== جلب أزرار الحلقات =====
async def get_episodes_markup(title, current_v_id):
    search_title = clean_name_strict(title)
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s ORDER BY ep_num ASC", (search_title,))
    if not res: return None
    
    btns, row, seen = [], [], set()
    me = await app.get_me()
    for vid, ep in res:
        if ep in seen: continue
        seen.add(ep)
        label = f"✅ {ep}" if str(vid) == str(current_v_id) else f"{ep}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
        if len(row) == 5:
            btns.append(row)
            row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

# ===== معالجة أمر Start (بدون اشتراك إجباري) =====
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك {message.from_user.first_name} في بوت المشاهدة!")
    
    v_id = message.command[1].strip()
    
    # 1. جلب البيانات من القاعدة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    title, ep = (res[0] if res and res[0] else (None, None))

    # 2. نظام التصحيح التلقائي (لو كانت 0 أو غير موجودة)
    if not title or ep == 0:
        try:
            m = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if m and m.caption:
                title = clean_name_strict(m.caption)
                # استخراج رقم الحلقة (أول رقم يظهر في الكابتشن بالكامل)
                ep_match = re.search(r'(\d+)', m.caption)
                ep = int(ep_match.group(1)) if ep_match else 0
                db_query("INSERT INTO videos (v_id, title, ep_num, status) VALUES (%s, %s, %s, 'posted') ON CONFLICT (v_id) DO UPDATE SET title=%s, ep_num=%s", (v_id, title, ep, title, ep), fetch=False)
        except:
            if not title: title, ep = "مسلسل", 0

    # 3. إرسال الحلقة مباشرة
    markup = await get_episodes_markup(title, v_id)
    caption = f"<b>📺 المسلسل : {visual_name(title)}</b>\n<b>🎞️ رقم الحلقة : {ep}</b>\n\n🍿 مشاهدة ممتعة!"

    try:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML)
    except:
        await message.reply_text("⚠️ عذراً، هذه الحلقة غير متوفرة حالياً.")

# ===== التشغيل =====
async def main():
    await app.start()
    logging.info("🚀 البوت يعمل الآن بنظام الأسماء الصارمة وبدون اشتراك إجباري...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
