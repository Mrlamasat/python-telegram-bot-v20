import re, psycopg2, asyncio
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- إعدادات محمد ---
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "ضع_توكن_البوت_هنا"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT title FROM videos ORDER BY title ASC;")
        titles = cur.fetchall()
        
        if not titles:
            return await message.reply_text("📭 لا توجد مسلسلات متاحة حالياً.")

        keyboard = []
        for title in titles:
            keyboard.append([InlineKeyboardButton(title[0], callback_data=f"show_{title[0][:20]}")]) # اختصار الاسم للبيانات
        
        await message.reply_text(
            "🎬 **أهلاً بك يا محمد**\n\nاختر المسلسل للمشاهدة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        cur.close(); conn.close()
    except Exception as e:
        print(f"❌ Error in start: {e}")

@app.on_callback_query(filters.regex(r"^show_"))
async def show_episodes(client, callback_query):
    try:
        # البحث عن الاسم الحقيقي للمسلسل
        short_name = callback_query.data.replace("show_", "")
        conn = get_db_connection()
        cur = conn.cursor()
        
        # جلب الحلقات مع التأكد من وجود v_id صالح
        cur.execute("SELECT ep_num, v_id FROM videos WHERE title LIKE %s AND v_id IS NOT NULL ORDER BY ep_num ASC;", (short_name + '%',))
        episodes = cur.fetchall()
        
        if not episodes:
            return await callback_query.answer("⚠️ لا توجد حلقات لهذا المسلسل حالياً.", show_alert=True)

        keyboard = []
        row = []
        for ep_num, v_id in episodes:
            if v_id: # التأكد من وجود معرف
                row.append(InlineKeyboardButton(f"حلقة {ep_num}", url=f"https://t.me/Ramadan4kTVBot?start={v_id}"))
            if len(row) == 3:
                keyboard.append(row); row = []
        if row: keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")])
        
        await callback_query.message.edit_text(
            f"📺 الحلقات المتاحة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        cur.close(); conn.close()
    except errors.MessageNotModified:
        pass
    except Exception as e:
        print(f"❌ Error in episodes: {e}")
        await callback_query.answer("حدث خطأ أثناء جلب الحلقات.")

@app.on_callback_query(filters.regex("back_to_main"))
async def back_to_main(client, callback_query):
    await start(client, callback_query.message)
    await callback_query.answer()

print("🚀 البوت يعمل الآن...")
app.run()
