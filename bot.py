import os
import psycopg2
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- إعدادات البوت (تأكد من وضع التوكن الخاص بك) ---
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "ضع_توكن_بوتك_هنا"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# دالة للاتصال بقاعدة البيانات
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

@app.on_message(filters.command("start"))
async def start(client, message):
    conn = get_db_connection()
    cur = conn.cursor()
    # جلب أسماء المسلسلات الفريدة
    cur.execute("SELECT DISTINCT title FROM videos ORDER BY title ASC;")
    titles = cur.fetchall()
    
    keyboard = []
    for title in titles:
        keyboard.append([InlineKeyboardButton(title[0], callback_data=f"show_{title[0]}")])
    
    await message.reply_text(
        "🎬 **أهلاً بك يا محمد في بوت المسلسلات**\n\nاختر المسلسل الذي تريد مشاهدته:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    cur.close()
    conn.close()

@app.on_callback_query(filters.regex(r"^show_"))
async def show_episodes(client, callback_query):
    series_name = callback_query.data.replace("show_", "")
    conn = get_db_connection()
    cur = conn.cursor()
    # جلب حلقات المسلسل المختار
    cur.execute("SELECT ep_num, v_id FROM videos WHERE title = %s ORDER BY ep_num ASC;", (series_name,))
    episodes = cur.fetchall()
    
    keyboard = []
    row = []
    for ep_num, v_id in episodes:
        # ترتيب الأزرار (3 أزرار في كل سطر)
        row.append(InlineKeyboardButton(f"حلقة {ep_num}", url=f"https://t.me/Ramadan4kTVBot?start={v_id}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_main")])
    
    await callback_query.message.edit_text(
        f"📺 **مسلسل: {series_name}**\nاختر الحلقة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    cur.close()
    conn.close()

@app.on_callback_query(filters.regex("back_to_main"))
async def back_to_main(client, callback_query):
    await start(client, callback_query.message)
    await callback_query.answer()

print("🚀 البوت يعمل الآن بنجاح...")
app.run()
