import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003689965691 # نفس قناة النشر الجديدة
ADMIN_ID = 7720165591

fixed_message_id = None
last_episode_count = 0
bot_info = None 

def get_series_list(db_query):
    return db_query("""
        SELECT series_name, COUNT(*), MAX(created_at), MAX(ep_num),
        (SELECT v_id FROM videos WHERE series_name = s.series_name ORDER BY ep_num DESC LIMIT 1)
        FROM videos s WHERE series_name IS NOT NULL GROUP BY series_name ORDER BY series_name
    """)

def create_series_keyboard(series_list, bot_username):
    keyboard = []
    row = []
    for item in series_list:
        s_name, count, last_date, max_ep, last_v_id = item
        btn_text = f"{s_name} 🔥" if (datetime.now() - last_date).total_seconds() < 86400 else s_name
        row.append(InlineKeyboardButton(btn_text, url=f"https://t.me/{bot_username}?start={last_v_id}"))
        if len(row) == 2: keyboard.append(row); row = []
    if row: keyboard.append(row)
    return keyboard

async def update_series_channel(client, db_query, force=False):
    global fixed_message_id, last_episode_count, bot_info
    res = db_query("SELECT COUNT(*) FROM videos")
    current_count = res[0][0] if res else 0
    if not force and current_count <= last_episode_count: return
    if not bot_info: bot_info = await client.get_me()
    
    series_list = get_series_list(db_query)
    if not series_list: return
    
    text = "🎬 **مكتبة المسلسلات الحصرية**\n━━━━━━━━━━━━━━━\nاختر المسلسل للمشاهدة 👇"
    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list, bot_info.username))

    try:
        if fixed_message_id:
            await client.edit_message_text(SERIES_CHANNEL, fixed_message_id, text, reply_markup=reply_markup)
        else:
            msg = await client.send_message(SERIES_CHANNEL, text, reply_markup=reply_markup)
            fixed_message_id = msg.id
        last_episode_count = current_count
    except: pass

def register_handlers(app, db_query):
    @app.on_message(filters.command("up_menu") & filters.user(ADMIN_ID))
    async def force_up(client, message):
        await update_series_channel(client, db_query, force=True)
        await message.reply("✅ تم تحديث القائمة")

def setup_series_menu(app, db_query):
    register_handlers(app, db_query)
    asyncio.get_event_loop().create_task(update_series_channel(app, db_query, force=True))

async def refresh_series_menu(client, db_query):
    await update_series_channel(client, db_query, force=True)
