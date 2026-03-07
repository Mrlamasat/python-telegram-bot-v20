import psycopg2
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- إعدادات محمد ---
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "7544026366:AAH6K9V0M59-N68mE22D9638E" # ضع التوكن هنا
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
SOURCE_CHANNEL = -1003547072209 

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

async def send_main_menu(message):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT title FROM videos ORDER BY title ASC;")
        titles = cur.fetchall()
        cur.close()
        conn.close()

        if not titles:
            text = "📭 القائمة فارغة حالياً."
            if hasattr(message, "edit_text"):
                await message.edit_text(text)
            else:
                await message.reply_text(text)
            return

        keyboard = []
        for title in titles:
            keyboard.append([InlineKeyboardButton(title[0], callback_data=f"show_{title[0][:20]}")])
        
        text = "🎬 **مرحباً بك في بوت المسلسلات**\n\nاختر المسلسل الذي تود متابعته:"
        if hasattr(message, "edit_text"):
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"❌ Error in menu: {e}")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        try:
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=SOURCE_CHANNEL,
                message_id=int(v_id)
            )
        except Exception as e:
            print(f"❌ Error sending video: {e}")
            await message.reply_text("⚠️ الفيديو غير متاح حالياً.")
    else:
        await send_main_menu(message)

@app.on_callback_query(filters.regex(r"^show_"))
async def show_episodes(client, callback_query):
    try:
        short_name = callback_query.data.replace("show_", "")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT ep_num, v_id FROM videos WHERE title LIKE %s ORDER BY ep_num ASC;", (short_name + '%',))
        episodes = cur.fetchall()
        cur.close()
        conn.close()

        if not episodes:
            await callback_query.answer("⚠️ لا توجد حلقات حالياً.", show_alert=True)
            return

        keyboard = []
        row = []
        me = await client.get_me()
        for ep_num, v_id in episodes:
            row.append(InlineKeyboardButton(f"حلقة {ep_num}", url=f"https://t.me/{me.username}?start={v_id}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_main")])
        
        await callback_query.message.edit_text(
            f"📺 **حلقات المسلسل المتاحة:**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except errors.MessageNotModified:
        pass
    except Exception as e:
        print(f"❌ Error in episodes: {e}")

@app.on_callback_query(filters.regex("back_to_main"))
async def back_to_main(client, callback_query):
    await send_main_menu(callback_query.message)
    await callback_query.answer()

if __name__ == "__main__":
    print("🚀 البوت يعمل الآن بنجاح...")
    app.run()
