import os
import psycopg2
import logging
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات (قراءة من Railway) =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
# سيقرأ التوكن من الـ Variables التي تضعها في موقع Railway باسم BOT_TOKEN
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"
ADMIN_ID = 7720165591

app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [2] قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

# ===== [3] عرض الحلقة مع أزرار التنقل =====
async def show_episode(client, message, v_id):
    # جلب بيانات الحلقة الحالية
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
    if not res: 
        await message.reply_text("❌ هذه الحلقة غير متوفرة.")
        return
    
    title, ep = res[0]
    
    # جلب الحلقة السابقة والتالية لنفس المسلسل
    prev_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND ep_num=%s", (title, ep-1))
    next_ep = db_query("SELECT v_id FROM videos WHERE title=%s AND ep_num=%s", (title, ep+1))

    # تسجيل المشاهدة
    db_query("INSERT INTO views_log (v_id) VALUES (%s)", (v_id,), fetch=False)
    db_query("UPDATE videos SET views = views + 1, last_view = NOW() WHERE v_id = %s", (v_id,), fetch=False)

    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {ep}</b>\n━━━━━━━━━━━━━━━"
    
    # بناء الأزرار
    buttons = []
    nav_row = []
    
    if prev_ep:
        nav_row.append(InlineKeyboardButton("⬅️ السابقة", callback_data=f"show_{prev_ep[0][0]}"))
    if next_ep:
        nav_row.append(InlineKeyboardButton("التالية ➡️", callback_data=f"show_{next_ep[0][0]}"))
    
    if nav_row: buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    markup = InlineKeyboardMarkup(buttons)
    
    # إذا كان الضغط من زر (callback)، نقوم بتعديل الرسالة، وإذا كان من /start نرسل رسالة جديدة
    if hasattr(message, "data"):
        await client.copy_message(message.message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)
    else:
        await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=caption, reply_markup=markup)

# معالج ضغطات الأزرار (Callback)
@app.on_callback_query(filters.regex(r"^show_"))
async def cb_show(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    await show_episode(client, callback_query, v_id)
    await callback_query.answer()

# [بقية الكود الخاص بالـ Stats والـ Handle_Source يبقى كما هو من رسالتك السابقة مع استبدال التوكن]
# ... (تأكد من نسخ دوال النشر والإحصائيات من الكود السابق)

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1: 
        await show_episode(client, message, message.command[1])
    else: 
        await message.reply_text(f"👋 أهلاً بك يا محمد.\nالبوت يعمل وجاهز لمشاهدة مسلسلات رمضان.")

if __name__ == "__main__":
    app.run()
