import logging
import psycopg2
import asyncio
import os
import re
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 1. الإعدادات (باستخدام IDs الرقمية)
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# المعرف الرقمي الذي زودتني به
ADMIN_CHANNEL = -1003547072209 

# ==============================
# 2. إعداد الحسابات
# ==============================
SESSION_STRING = os.environ.get("USER_SESSION")

user_app = Client("user_worker", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)
bot_app = Client("bot_manager", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH, in_memory=True)

def db_query(query, params=(), commit=False, fetchone=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if commit: conn.commit()
        res = cur.fetchone() if fetchone else None
        cur.close()
        return res
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# ==============================
# 3. دالة السحب الذكي (Smart Import)
# ==============================
async def run_import(status_msg):
    count = 0
    try:
        if not user_app.is_connected: await user_app.start()
        
        print(f"📡 بدء سحب التاريخ من القناة ID: {ADMIN_CHANNEL}")
        
        async for msg in user_app.get_chat_history(ADMIN_CHANNEL, limit=500):
            # سحب الرسالة سواء كانت ميديا أو نص يحتوي على "🧠 Explanations"
            content_text = msg.caption or msg.text or ""
            
            # فلتر: هل الرسالة تحتوي على محتوى مفيد؟
            if content_text or msg.video or msg.document:
                # استخراج العنوان (أول سطر)
                lines = content_text.split('\n')
                title = lines[0].strip() if lines[0] else "محتوى من القناة"
                
                # استخراج رقم (للتنظيم)
                nums = re.findall(r'\d+', content_text)
                ep_num = int(nums[0]) if nums else 1

                # حفظ المسلسل
                db_query("INSERT INTO series (title) VALUES (%s) ON CONFLICT (title) DO NOTHING", (title,), commit=True)
                s_res = db_query("SELECT id FROM series WHERE title=%s", (title,), fetchone=True)
                
                if s_res:
                    # تخزين الرسالة كـ "حلقة" باستخدام ID الرسالة
                    db_query("""
                        INSERT INTO episodes (v_id, series_id, title, ep_num, quality)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (v_id) DO NOTHING
                    """, (str(msg.id), s_res['id'], title, ep_num, "HD"), commit=True)
                    count += 1
        
        await status_msg.edit_text(f"✅ اكتمل السحب بنجاح يا محمد!\n📦 إجمالي الرسائل المسجلة: {count}")
    except Exception as e:
        print(f"Error: {e}")
        await status_msg.edit_text(f"❌ حدث خطأ أثناء السحب: {str(e)[:100]}")

@bot_app.on_message(filters.command("import_updated") & filters.private)
async def start_import_cmd(client, message):
    status = await message.reply_text("🔄 جاري سحب كافة البيانات والأدوات من القناة...")
    asyncio.create_task(run_import(status))

@bot_app.on_message(filters.command("start") & filters.private)
async def start_bot(client, message):
    await message.reply_text("🎬 أهلاً بك يا محمد المحسن.\nالبوت جاهز لعرض محتوى القناة.")

# ==============================
# 5. التشغيل
# ==============================
async def main():
    await bot_app.start()
    print("🚀 البوت يعمل الآن..")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
