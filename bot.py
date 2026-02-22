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
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# ==============================
# 2. إعداد الحسابات (User + Bot)
# ==============================
SESSION_STRING = os.environ.get("USER_SESSION")

# الحساب الشخصي (للسحب)
user_app = Client(
    name="user_worker",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    in_memory=True
)

# البوت (للتفاعل)
bot_app = Client(
    name="bot_manager",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
    in_memory=True
)

# --- دالة قاعدة البيانات ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None)
        if commit: conn.commit()
        cur.close()
        return result
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# ==============================
# 3. أمر السحب (IMPORT)
# ==============================
@bot_app.on_message(filters.command("import_updated") & filters.private)
async def import_updated_series(client, message):
    status = await message.reply_text("🔄 جاري السحب ومعالجة البيانات...")
    count = 0
    try:
        # التأكد من تشغيل الحساب الشخصي للسحب
        if not user_app.is_connected:
            await user_app.start()

        target_chat = await user_app.get_chat(ADMIN_CHANNEL)
        
        async for msg in user_app.get_chat_history(target_chat.id):
            is_video = msg.video or (msg.document and msg.document.mime_type and "video" in msg.document.mime_type)
            
            if is_video:
                caption = (msg.caption or "").strip()
                media_info = msg.video or msg.document
                file_name = getattr(media_info, "file_name", "") or ""

                if caption:
                    clean_title = caption.split('\n')[0].replace('🎬', '').strip()
                else:
                    clean_title = file_name if file_name else "مسلسل غير معروف"

                # استخراج رقم الحلقة
                text_to_search = f"{caption} {file_name}"
                nums = re.findall(r'\d+', text_to_search)
                ep_num = int(nums[0]) if nums else 1

                # حفظ في قاعدة البيانات
                db_query("INSERT INTO series (title) VALUES (%s) ON CONFLICT (title) DO NOTHING", (clean_title,), commit=True)
                s_res = db_query("SELECT id FROM series WHERE title=%s", (clean_title,), fetchone=True)
                
                if s_res:
                    db_query("""
                        INSERT INTO episodes (v_id, series_id, title, ep_num, quality)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (v_id) DO UPDATE SET series_id=EXCLUDED.series_id, ep_num=EXCLUDED.ep_num
                    """, (str(msg.id), s_res['id'], clean_title, ep_num, "1080p"), commit=True)
                    count += 1
                    if count % 20 == 0:
                        await status.edit_text(f"🔄 جاري السحب.. تم العثور على {count} حلقة.")

        await status.edit_text(f"✅ اكتمل السحب بنجاح!\n📦 تم تسجيل {count} حلقة.")
    except Exception as e:
        await status.edit_text(f"❌ حدث خطأ: {e}")

# ==============================
# 4. نظام المشاهدة
# ==============================
@bot_app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text(f"🎬 أهلاً بك يا محمد.\nاستخدم الروابط من القناة للمشاهدة.")

    param = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (str(param),), fetchone=True)
    
    if data:
        related = db_query("SELECT v_id, ep_num FROM episodes WHERE series_id=%s ORDER BY ep_num ASC", (data['series_id'],), fetchall=True)
        bot_info = await client.get_me()
        buttons, row = [], []
        for ep in related:
            label = f"🔹 {ep['ep_num']}" if str(ep['v_id']) == str(param) else f"{ep['ep_num']}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={ep['v_id']}"))
            if len(row) == 5: buttons.append(row); row = []
        if row: buttons.append(row)
        
        buttons.append([InlineKeyboardButton("🍿 القناة الرئيسية", url="https://t.me/MoAlmohsen")])

        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=ADMIN_CHANNEL,
            message_id=int(data['v_id']),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await message.reply_text("❌ لم يتم العثور على الحلقة.")

# ==============================
# 5. تشغيل البوت والحساب معاً
# ==============================
async def start_services():
    await bot_app.start()
    # الحساب الشخصي لا نشغله إلا عند طلب السحب لتوفير الموارد
    print("🚀 الروبوت يعمل الآن ومستعد لخدمتك يا محمد.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        pass
