import os
import psycopg2
import psycopg2.pool
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
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209      
PUBLIC_POST_CHANNEL = -1003554018307  
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("mohammed_bot_railway", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== إدارة قاعدة البيانات =====
db_pool = None
def get_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")
    return db_pool

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        pool = get_pool()
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        return res
    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: get_pool().putconn(conn)

def init_db():
    db_query("""CREATE TABLE IF NOT EXISTS videos (
        v_id TEXT PRIMARY KEY, title TEXT, ep_num INTEGER, 
        poster_id TEXT, quality TEXT, duration TEXT, 
        status TEXT DEFAULT 'waiting', views INTEGER DEFAULT 0
    )""", fetch=False)

# ===== أدوات المعالجة والتنظيف =====
def clean_string(text):
    """تنظيف النصوص من النقاط والمسافات للمقارنة البرمجية"""
    if not text: return ""
    return text.replace(".", "").replace(" ", "").replace("🎬", "").strip()

def obfuscate_visual(text):
    """إضافة نقاط للاسم عند العرض فقط للتمويه"""
    if not text: return ""
    clean = text.replace(".", "").replace(" ", "")
    return " . ".join(list(clean))

# ===== دالة جلب الأزرار (النسخة الذكية) =====
async def get_episodes_markup(title, current_v_id):
    """جلب الحلقات مع تنظيف الاسم لضمان التطابق التام"""
    search_title = clean_string(title)
    
    # جلب الحلقات المنشورة فقط
    res = db_query("SELECT v_id, ep_num, title FROM videos WHERE status = 'posted' ORDER BY ep_num ASC", fetch=True)
    
    if not res:
        return None
    
    btns, row, seen = [], [], set()
    me = await app.get_me()
    
    for vid, ep, t in res:
        # مقارنة الاسم المنظف في القاعدة مع الاسم المنظف المطلوب
        if clean_string(t) == search_title:
            if ep in seen: continue
            seen.add(ep)
            label = f"✅ {ep}" if str(vid) == str(current_v_id) else f"{ep}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{me.username}?start={vid}"))
            
            if len(row) == 5:
                btns.append(row)
                row = []
    
    if row:
        btns.append(row)
    
    return InlineKeyboardMarkup(btns) if btns else None

# ===== دالة إرسال الفيديو =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep):
    try:
        # جلب الأزرار بناءً على الاسم (سيعمل حتى لو الاسم فيه نقاط)
        markup = await get_episodes_markup(title, v_id)
        
        # فحص الاشتراك الإجباري
        is_sub = True
        try:
            member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
            if member.status in ["left", "kicked"]: is_sub = False
        except: is_sub = False

        cap = (f"<b>📺 المسلسل : {obfuscate_visual(title)}</b>\n"
               f"<b>🎞️ رقم الحلقة : {ep}</b>\n\n🍿 مشاهدة ممتعة!")

        # تجهيز الكيبورد النهائي
        final_kb = []
        if not is_sub:
            final_kb.append([InlineKeyboardButton("📥 انضمام للقناة", url=FORCE_SUB_LINK)])
        
        if markup:
            for r in markup.inline_keyboard:
                final_kb.append(r)

        await client.copy_message(
            chat_id=chat_id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=cap,
            reply_markup=InlineKeyboardMarkup(final_kb) if final_kb else None
        )
    except Exception as e:
        logging.error(f"❌ Error sending: {e}")
        await client.send_message(chat_id, "⚠️ عذراً، الحلقة غير متوفرة حالياً.")

# ===== معالجة الأوامر =====
@app.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"أهلاً بك {message.from_user.first_name} في بوت المشاهدة!")
    
    v_id = message.command[1]
    # جلب بيانات الحلقة من القاعدة (التي قمنا بتصحيحها في ترمكس)
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id=%s", (v_id,))
    
    if res:
        title, ep = res[0]
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, title, ep)
    else:
        # إذا لم تكن موجودة في القاعدة، نرسلها كحلقة مجهولة (سيتم تحديثها لاحقاً)
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, "مسلسل", 0)

# ===== المزامنة (للطوارئ فقط) =====
@app.on_message(filters.command("sync") & filters.user(ADMIN_ID))
async def sync_bot(client, message):
    await message.reply_text("💡 تم تنفيذ المزامنة العميقة من Termux بنجاح. البوت الآن يقرأ من قاعدة البيانات المحدثة.")

# ===== التشغيل =====
async def main():
    await app.start()
    logging.info("🚀 البوت يعمل الآن في Railway...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    init_db()
    app.run(main())
