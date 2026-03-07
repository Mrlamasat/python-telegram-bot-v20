import os
import psycopg2
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("railway_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

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

# ===== [2] دالة عرض الحلقة (إصلاح الـ NULL والـ 5 أزرار) =====
async def show_episode(client, message, v_id, edit=False):
    # جلب البيانات من القاعدة
    res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (str(v_id),))
    if not res:
        return

    title, current_ep = res[0]
    
    # جلب جميع حلقات المسلسل لترتيب الأزرار
    all_eps = db_query("SELECT ep_num, v_id FROM videos WHERE title = %s ORDER BY ep_num ASC", (title,))
    
    caption = f"<b>📺 {title}</b>\n<b>🎬 الحلقة رقم: {current_ep}</b>\n━━━━━━━━━━━━━━━"
    
    # بناء الأزرار: 5 في كل سطر
    buttons = []
    row = []
    for ep_n, ep_vid in all_eps:
        btn_text = f"• {ep_n} •" if str(ep_vid) == str(v_id) else str(ep_n)
        row.append(InlineKeyboardButton(btn_text, callback_data=f"go_{ep_vid}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔗 قناة الاحتياط", url=BACKUP_CHANNEL_LINK)])

    chat_id = message.message.chat.id if hasattr(message, "data") else message.chat.id

    try:
        # إذا كان ضغط زر (نفس المكان)، نحذف القديمة
        if edit and hasattr(message, "data"):
            await message.message.delete()

        # إرسال الفيديو (استخدام int(v_id) للنسخ من القناة)
        await client.copy_message(
            chat_id=chat_id,
            from_chat_id=SOURCE_CHANNEL,
            message_id=int(v_id),
            caption=caption,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logging.error(f"فشل في جلب الحلقة {v_id}: {e}")

@app.on_callback_query(filters.regex(r"^go_"))
async def nav_handler(client, query):
    v_id = query.data.split("_")[1]
    await show_episode(client, query, v_id, edit=True)
    await query.answer()

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text("أهلاً بك يا محمد، البوت جاهز.")

if __name__ == "__main__":
    app.run()
