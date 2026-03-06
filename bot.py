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

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# القنوات والآدمن
SOURCE_CHANNEL = -1003547072209 
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 111111111  # 💡 ضاع آيدي حسابك هنا يا محمد لكي تظهر لك ميزات النشر

app = Client("mohammed_bot_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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
        logging.error(f"❌ DB Error: {e}")
        if conn: conn.close()
        return None

# ===== أدوات التنظيف والعرض =====
def clean_name(text):
    if not text: return "مسلسل"
    # تنظيف السطر الأول ليصبح معرفاً موحداً
    t = re.sub(r'[^\w\s]', '', text)
    return t.replace(".", "").replace(" ", "").strip()

def visual_name(text):
    """عرض الاسم بنقاط (م . و . ل . ا . ن . ا)"""
    clean = clean_name(text)
    return " . ".join(list(clean))

# ===== جلب أزرار الحلقات =====
async def get_episodes_markup(title, current_v_id):
    search_title = clean_name(title)
    res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s ORDER BY ep_num ASC", (search_title,))
    
    if not res: return None
    
    btns, row, seen = [], [], set()
    me = await app.get_me()
    
    for vid, ep in res:
        if ep in seen: continue
        seen.add(ep)
        # زر الحلقة الحالية يكون عليه علامة ✅
        label = f"✅ {ep}" if str(vid) == str(current_v_id) else f"{ep}"
        row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
        
        if len(row) == 5:
            btns.append(row)
            row = []
    
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

# ===== معالجة أمر Start والتصحيح التلقائي =====
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك {message.from_user.first_name} في بوت المشاهدة!")
    
    v_id = message.command[1].strip()
    
    # 1. البحث في القاعدة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    
    title, ep = None, None
    if res and res[0]:
        title, ep = res[0]
    
    # 2. نظام التصحيح التلقائي (لو كانت 0 أو غير موجودة)
    if not title or ep == 0:
        try:
            m = await client.get_messages(SOURCE_CHANNEL, int(v_id))
            if m and m.caption:
                lines = [l.strip() for l in m.caption.split('\n') if l.strip()]
                title = clean_name(lines[0])
                # البحث عن رقم الحلقة بذكاء (السطر الثالث أو أول رقم)
                ep_match = re.search(r'\[(\d+)\]', m.caption) or re.search(r'(\d+)', m.caption)
                ep = int(ep_match.group(1)) if ep_match else 0
                
                # حفظ التصحيح فوراً
                db_query("""
                    INSERT INTO videos (v_id, title, ep_num, status) 
                    VALUES (%s, %s, %s, 'posted') 
                    ON CONFLICT (v_id) 
                    DO UPDATE SET title=%s, ep_num=%s
                """, (v_id, title, ep, title, ep), fetch=False)
        except:
            if not title: title, ep = "مسلسل", 0

    # 3. الاشتراك الإجباري
    try:
        await client.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
    except:
        return await message.reply_text(
            f"⚠️ عذراً، يجب عليك الاشتراك في القناة أولاً لتتمكن من المشاهدة.\n\n{FORCE_SUB_LINK}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 اضغط هنا للاشتراك", url=FORCE_SUB_LINK)]])
        )

    # 4. الإرسال النهائي
    markup = await get_episodes_markup(title, v_id)
    caption = (f"<b>📺 المسلسل : {visual_name(title)}</b>\n"
               f"<b>🎞️ رقم الحلقة : {ep}</b>\n\n🍿 مشاهدة ممتعة!")

    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=caption,
            reply_markup=markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.reply_text("⚠️ هذه الحلقة لم تعد موجودة في المصدر.")

# ===== حماية ميزات الآدمن =====
@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    # إذا لم يكن المستخدم هو الآدمن، نتجاهل أي ضغطة تحاول إظهار "تم النشر"
    if callback_query.from_user.id != ADMIN_ID:
        return await callback_query.answer("⚠️ ليس لديك صلاحية الوصول.", show_alert=True)
    
    # هنا تضع أوامرك الخاصة بالنشر إذا أردت مستقبلاً
    if callback_query.data == "confirm_post":
        await callback_query.answer("✅ تم النشر باحترافية!", show_alert=True)

# ===== التشغيل =====
async def main():
    await app.start()
    logging.info("🚀 البوت يعمل الآن بنظام التصحيح وحماية الآدمن...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(main())
