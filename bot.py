import logging
import psycopg2
import asyncio
import os
import re
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 1. الإعدادات
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
ADMIN_CHANNEL = "@Ramadan4kTV" 

# ==============================
# 2. إعداد الحسابات
# ==============================
SESSION_STRING = os.environ.get("USER_SESSION")

# حساب المستخدم (User)
user_app = Client("user_worker", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)
# حساب البوت (Bot)
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
# 3. دالة السحب (المحسنة جداً)
# ==============================
async def run_import(status_msg):
    count = 0
    try:
        if not user_app.is_connected: await user_app.start()
        
        # الحصول على المعرف الرقمي للقناة لتجنب مشاكل الـ Peer
        chat = await user_app.get_chat(ADMIN_CHANNEL)
        
        async for msg in user_app.get_chat_history(chat.id, limit=300):
            # نقبل أي رسالة تحتوي على ميديا (فيديو أو مستند)
            media = msg.video or msg.document
            if media:
                caption = (msg.caption or "").strip()
                file_name = getattr(media, "file_name", "") or ""
                
                # استخراج الاسم
                title = caption.split('\n')[0].replace('🎬', '').strip() if caption else file_name
                if not title: title = "مسلسل غير معروف"
                
                # استخراج الرقم
                nums = re.findall(r'\d+', f"{caption} {file_name}")
                ep_num = int(nums[-1]) if nums else 1

                # تخزين المسلسل
                db_query("INSERT INTO series (title) VALUES (%s) ON CONFLICT (title) DO NOTHING", (title,), commit=True)
                s_res = db_query("SELECT id FROM series WHERE title=%s", (title,), fetchone=True)
                
                if s_res:
                    db_query("""
                        INSERT INTO episodes (v_id, series_id, title, ep_num, quality)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (v_id) DO NOTHING
                    """, (str(msg.id), s_res['id'], title, ep_num, "1080p"), commit=True)
                    count += 1
        
        await status_msg.edit_text(f"✅ تم السحب بنجاح!\n📦 إجمالي الملفات المضافة: {count}")
    except Exception as e:
        await status_msg.edit_text(f"❌ خطأ تقني: {str(e)[:100]}")

@bot_app.on_message(filters.command("import_updated") & filters.private)
async def start_import_cmd(client, message):
    status = await message.reply_text("🔄 بدأت عملية السحب، يرجى الانتظار...")
    # تشغيل السحب في الخلفية لعدم تعطيل البوت
    asyncio.create_task(run_import(status))

@bot_app.on_message(filters.command("start") & filters.private)
async def start_bot(client, message):
    await message.reply_text("🎬 أهلاً بك يا محمد في بوت إدارة المسلسلات.")

# ==============================
# 5. تشغيل البوت
# ==============================
async def main():
    await bot_app.start()
    print("🚀 البوت يعمل الآن..")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
