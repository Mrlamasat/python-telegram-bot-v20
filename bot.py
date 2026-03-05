import os
import psycopg2
import psycopg2.pool
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== Ø§Ù„Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§Ù„Ø£Ø³Ø§Ø³ÙŠØ© =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
FORCE_SUB_CHANNEL = -1003894735143
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Connection Pool =====
db_pool = None

def get_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode="require")
    return db_pool

# ===== Ù‚Ø§Ø¹Ø¯Ø© Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª =====
def db_query(query, params=(), fetch=True):
    conn = None
    try:
        pool = get_pool()
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        return result
    except Exception as e:
        logging.error(f"âŒ Database Error: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            get_pool().putconn(conn)

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER,
            poster_id TEXT,
            quality TEXT,
            duration TEXT,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    logging.info("âœ… Database initialized.")

# ===== Ø§Ù„Ø¯ÙˆØ§Ù„ Ø§Ù„Ù…Ø³Ø§Ø¹Ø¯Ø© =====
def obfuscate_visual(text):
    if not text:
        return ""
    return " . ".join(list(text))

def clean_series_title(text):
    if not text:
        return "Ù…Ø³Ù„Ø³Ù„"
    return re.sub(r'(Ø§Ù„Ø­Ù„Ù‚Ø©|Ø­Ù„Ù‚Ø©)?\s*\d+', '', text).strip()

async def get_episodes_markup(title, current_v_id):
    # CAST Ù„Ø¶Ù…Ø§Ù† Ø§Ù„ØªØ±ØªÙŠØ¨ Ø§Ù„Ø±Ù‚Ù…ÙŠ Ø§Ù„ØµØ­ÙŠØ­ 1, 2, 10 ÙˆÙ„ÙŠØ³ 1, 10, 2
    res = db_query(
        "SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY CAST(ep_num AS INTEGER) ASC",
        (title,)
    )
    if not res:
        return []
    buttons, row, seen_eps = [], [], set()
    bot_info = await app.get_me()
    for v_id, ep_num in res:
        if ep_num in seen_eps:
            continue
        seen_eps.add(ep_num)
        label = f"âœ…ï¸ {ep_num}" if str(v_id) == str(current_v_id) else f"{ep_num}"
        btn = InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={v_id}")
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons

async def check_subscription(client, user_id):
    if user_id == ADMIN_ID:
        return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.warning(f"âš ï¸ check_subscription error for {user_id}: {e}")
        return False

# ===== Ø¥Ø±Ø³Ø§Ù„ Ø§Ù„ÙÙŠØ¯ÙŠÙˆ Ø§Ù„Ù†Ù‡Ø§Ø¦ÙŠ Ù„Ù„Ù…Ø³ØªØ®Ø¯Ù… =====
async def send_video_final(client, chat_id, user_id, v_id, title, ep, q, dur):
    # ØªØ­Ø¯ÙŠØ« Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª Ù…Ù† Ø§Ù„Ø³ÙˆØ±Ø³ Ù‚Ø¨Ù„ Ø§Ù„Ø¥Ø±Ø³Ø§Ù„
    try:
        source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
        if source_msg and source_msg.caption:
            new_title = clean_series_title(source_msg.caption)
            ep_match = re.search(r'(\d+)', source_msg.caption)
            if new_title:
                title = new_title
            if ep_match:
                ep = int(ep_match.group(1))
            db_query("UPDATE videos SET title=%s, ep_num=%s WHERE v_id=%s", (title, ep, v_id), fetch=False)
    except Exception as e:
        logging.warning(f"âš ï¸ Could not fetch source message {v_id}: {e}")

    db_query("UPDATE videos SET views = COALESCE(views, 0) + 1 WHERE v_id = %s", (v_id,), fetch=False)
    btns = await get_episodes_markup(title, v_id)
    is_subscribed = await check_subscription(client, user_id)

    safe_title = obfuscate_visual(escape(title))
    info_text = (
        f"<b>ðŸ“º Ø§Ù„Ù…Ø³Ù„Ø³Ù„ : {safe_title}</b>\n"
        f"<b>ðŸŽžï¸ Ø±Ù‚Ù… Ø§Ù„Ø­Ù„Ù‚Ø© : {escape(str(ep))}</b>\n"
        f"<b>ðŸ’¿ Ø§Ù„Ø¬ÙˆØ¯Ø© : {escape(str(q))}</b>\n"
        f"<b>â³ Ø§Ù„Ù…Ø¯Ø© : {escape(str(dur))}</b>"
    )
    cap = f"{info_text}\n\nðŸ¿ <b>Ù…Ø´Ø§Ù‡Ø¯Ø© Ù…Ù…ØªØ¹Ø© Ù†ØªÙ…Ù†Ø§Ù‡Ø§ Ù„ÙƒÙ…!</b>"

    if not is_subscribed:
        cap += f"\n\nâš ï¸ <b>Ø§Ù†Ø¶Ù… Ù„Ù„Ù‚Ù†Ø§Ø© Ù„Ù…ØªØ§Ø¨Ø¹Ø© Ø§Ù„Ø­Ù„Ù‚Ø§Øª Ø§Ù„Ù‚Ø§Ø¯Ù…Ø© ðŸ‘‡</b>"
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("ðŸ“¥ Ø§Ù†Ø¶Ù…Ø§Ù… (Ù…Ù‡Ù…)", url=FORCE_SUB_LINK)]] + (btns if btns else [])
        )
    else:
        markup = InlineKeyboardMarkup(btns) if btns else None

    try:
        await client.copy_message(
            chat_id, SOURCE_CHANNEL, int(v_id),
            caption=cap, parse_mode=ParseMode.HTML, reply_markup=markup
        )
    except Exception as e:
        logging.error(f"âŒ copy_message failed: {e}")
        await client.send_message(chat_id, f"ðŸŽ¬ {safe_title} - Ø­Ù„Ù‚Ø© {ep}")

# ===== Ø£ÙˆØ§Ù…Ø± Ø§Ù„Ø¥Ø¯Ø§Ø±Ø© =====

@app.on_message(filters.command("clear") & (filters.user(ADMIN_ID) | filters.chat(SOURCE_CHANNEL)))
async def clear_handler(client, message):
    db_query("DELETE FROM videos WHERE status != 'posted'", fetch=False)
    await message.reply_text("âœ… ØªÙ… ØªÙ†Ø¸ÙŠÙ Ø¹Ù…Ù„ÙŠØ§Øª Ø§Ù„Ø±ÙØ¹ ØºÙŠØ± Ø§Ù„Ù…ÙƒØªÙ…Ù„Ø©.")

@app.on_message(filters.command("del") & filters.user(ADMIN_ID))
async def delete_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text("ðŸ“ Ø§Ø±Ø³Ù„: `/del Ø§Ø³Ù…_Ø§Ù„Ù…Ø³Ù„Ø³Ù„ Ø±Ù‚Ù…_Ø§Ù„Ø­Ù„Ù‚Ø©` Ù„Ù„Ø­Ø°Ù.")

    full_text = message.text.replace("/del ", "", 1).strip()
    # Ø§Ø³ØªØ®Ø±Ø§Ø¬ Ø§Ù„Ø§Ø³Ù… ÙˆØ§Ù„Ø±Ù‚Ù… Ø¨Ø´ÙƒÙ„ ØµØ­ÙŠØ­
    match = re.match(r'^(.+?)\s+(\d+)$', full_text)
    if match:
        title = match.group(1).strip()
        ep = match.group(2)
        db_query("DELETE FROM videos WHERE title = %s AND ep_num = %s", (title, int(ep)), fetch=False)
        await message.reply_text(f"ðŸ—‘ï¸ ØªÙ… Ø­Ø°Ù Ù…Ø³Ù„Ø³Ù„ {title} Ø­Ù„Ù‚Ø© {ep} Ø¨Ù†Ø¬Ø§Ø­.")
    else:
        await message.reply_text("âŒ Ù„Ù… Ø£Ø³ØªØ·Ø¹ ØªØ­Ø¯ÙŠØ¯ Ø±Ù‚Ù… Ø§Ù„Ø­Ù„Ù‚Ø©.\nØ§Ù„ØµÙŠØºØ© Ø§Ù„ØµØ­ÙŠØ­Ø©: `/del Ø§Ø³Ù…_Ø§Ù„Ù…Ø³Ù„Ø³Ù„ Ø±Ù‚Ù…_Ø§Ù„Ø­Ù„Ù‚Ø©`")

# ===== Ø§Ø³ØªÙ‚Ø¨Ø§Ù„ Ø§Ù„ÙÙŠØ¯ÙŠÙˆ =====

@app.on_message(filters.chat(SOURCE_CHANNEL) & (filters.video | filters.document | filters.animation))
async def receive_video(client, message):
    v_id = str(message.id)
    # Ø¯Ø¹Ù… video Ùˆ animation Ùˆ document
    media = message.video or message.animation
    if media and hasattr(media, 'duration') and media.duration:
        d = media.duration
    else:
        d = 0
    dur = f"{d // 3600:02}:{(d % 3600) // 60:02}:{d % 60:02}"
    db_query(
        "INSERT INTO videos (v_id, status, duration) VALUES (%s, 'waiting', %s) ON CONFLICT (v_id) DO UPDATE SET status='waiting', duration=%s",
        (v_id, dur, dur), fetch=False
    )
    await message.reply_text(f"âœ… ØªÙ… Ø§Ù„Ù…Ø±ÙÙ‚ ({dur}). Ø£Ø±Ø³Ù„ Ø§Ù„Ø¨ÙˆØ³ØªØ± Ø§Ù„Ø¢Ù†.")

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.photo)
async def receive_poster(client, message):
    # CAST Ù„Ø¶Ù…Ø§Ù† Ø¬Ù„Ø¨ Ø¢Ø®Ø± v_id Ø±Ù‚Ù…ÙŠØ§Ù‹ ÙˆÙ„ÙŠØ³ Ù†ØµÙŠØ§Ù‹
    res = db_query(
        "SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1"
    )
    if not res:
        return
    v_id = res[0][0]
    # caption Ù‚Ø¯ ÙŠÙƒÙˆÙ† None
    title = clean_series_title(message.caption or "")
    db_query(
        "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_quality' WHERE v_id=%s",
        (title, message.photo.file_id, v_id), fetch=False
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("4K", callback_data=f"q_4K_{v_id}"),
        InlineKeyboardButton("HD", callback_data=f"q_HD_{v_id}"),
        InlineKeyboardButton("SD", callback_data=f"q_SD_{v_id}")
    ]])
    await message.reply_text(
        f"ðŸ“Œ Ø§Ù„Ù…Ø³Ù„Ø³Ù„: <b>{escape(title)}</b>\nØ§Ø®ØªØ± Ø§Ù„Ø¬ÙˆØ¯Ø©:",
        reply_markup=markup, parse_mode=ParseMode.HTML
    )

@app.on_callback_query(filters.regex("^q_"))
async def set_quality(client, cb):
    # split Ù…Ø±ØªÙŠÙ† ÙÙ‚Ø· Ù„ØªØ¬Ù†Ø¨ Ù…Ø´ÙƒÙ„Ø© v_id Ø§Ù„Ø°ÙŠ ÙŠØ­ØªÙˆÙŠ _
    parts = cb.data.split("_", 2)
    if len(parts) != 3:
        return await cb.answer("âŒ Ø¨ÙŠØ§Ù†Ø§Øª ØºÙŠØ± ØµØ§Ù„Ø­Ø©")
    _, q, v_id = parts
    db_query("UPDATE videos SET quality=%s, status='awaiting_ep' WHERE v_id=%s", (q, v_id), fetch=False)
    await cb.message.edit_text(f"âœ… Ø§Ù„Ø¬ÙˆØ¯Ø©: <b>{q}</b>. Ø£Ø±Ø³Ù„ Ø§Ù„Ø¢Ù† Ø±Ù‚Ù… Ø§Ù„Ø­Ù„Ù‚Ø©:", parse_mode=ParseMode.HTML)

@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.text & ~filters.command(["start", "stats", "del", "clear"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit():
        return
    # CAST Ù„Ø¶Ù…Ø§Ù† Ø¬Ù„Ø¨ Ø¢Ø®Ø± v_id Ø±Ù‚Ù…ÙŠØ§Ù‹ ÙˆÙ„ÙŠØ³ Ù†ØµÙŠØ§Ù‹ â† Ù‡Ø°Ø§ ÙƒØ§Ù† Ø³Ø¨Ø¨ Ù…Ø´ÙƒÙ„ØªÙƒ Ø§Ù„Ø±Ø¦ÙŠØ³ÙŠØ©
    res = db_query(
        "SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1"
    )
    if not res:
        return
    v_id, title, p_id, q, dur = res[0]
    ep_num = int(message.text)
    db_query("UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s", (ep_num, v_id), fetch=False)

    b_info = await client.get_me()
    safe_t = obfuscate_visual(escape(title))
    caption = (
        f"ðŸŽ¬ <b>{safe_t}</b>\n\n"
        f"<b>Ø§Ù„Ø­Ù„Ù‚Ø©: [{ep_num}]</b>\n"
        f"<b>Ø§Ù„Ø¬ÙˆØ¯Ø©: [{q}]</b>\n"
        f"<b>Ø§Ù„Ù…Ø¯Ø©: [{dur}]</b>\n\n"
        f"Ù†ØªÙ…Ù†Ù‰ Ù„ÙƒÙ… Ù…Ø´Ø§Ù‡Ø¯Ø© Ù…Ù…ØªØ¹Ø©."
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("â–¶ï¸ Ù…Ø´Ø§Ù‡Ø¯Ø© Ø§Ù„Ø­Ù„Ù‚Ø©", url=f"https://t.me/{b_info.username}?start={v_id}")
    ]])

    try:
        await client.send_photo(
            chat_id=PUBLIC_POST_CHANNEL, photo=p_id,
            caption=caption, reply_markup=markup, parse_mode=ParseMode.HTML
        )
        await message.reply_text("ðŸš€ ØªÙ… Ø§Ù„Ù†Ø´Ø± ÙÙŠ Ø§Ù„Ù‚Ù†Ø§Ø© Ø¨Ù†Ø¬Ø§Ø­.")
    except Exception as e:
        logging.error(f"âŒ ÙØ´Ù„ Ø§Ù„Ù†Ø´Ø±: {e}")
        await message.reply_text(f"âŒ ÙØ´Ù„ Ø§Ù„Ù†Ø´Ø±.\nØ§Ù„Ø®Ø·Ø£: {e}")

# ===== Ø£ÙˆØ§Ù…Ø± Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù… =====

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        await message.reply_text(
            f"Ø£Ù‡Ù„Ø§Ù‹ Ø¨Ùƒ ÙŠØ§ <b>{escape(message.from_user.first_name)}</b>! ðŸ‘‹",
            parse_mode=ParseMode.HTML
        )
        return
    v_id = message.command[1]
    res = db_query("SELECT title, ep_num, quality, duration FROM videos WHERE v_id=%s", (v_id,))
    if res:
        await send_video_final(client, message.chat.id, message.from_user.id, v_id, *res[0])
    else:
        await message.reply_text("âŒ Ù„Ù… ÙŠØªÙ… Ø§Ù„Ø¹Ø«ÙˆØ± Ø¹Ù„Ù‰ Ù‡Ø°Ø§ Ø§Ù„ÙÙŠØ¯ÙŠÙˆ.")

@app.on_message(filters.command("stats") & filters.private)
async def get_stats(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    top = db_query(
        "SELECT title, ep_num, views FROM videos WHERE status='posted' ORDER BY views DESC LIMIT 10"
    )
    text = "ðŸ“Š <b>ØªÙ‚Ø±ÙŠØ± Ø§Ù„Ø£Ø¯Ø§Ø¡ (Ø§Ù„Ø£ÙƒØ«Ø± Ù…Ø´Ø§Ù‡Ø¯Ø©):</b>\n\n"
    if top:
        for i, r in enumerate(top, 1):
            text += f"{i}. ðŸŽ¬ <b>{escape(str(r[0]))}</b>\nâ”” Ø­Ù„Ù‚Ø© {r[1]} â† ðŸ‘¤ <b>{r[2]} Ù…Ø´Ø§Ù‡Ø¯Ø©</b>\n\n"
    else:
        text += "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ø¨Ø¹Ø¯."
    await message.reply_text(text, parse_mode=ParseMode.HTML)

# ===== Ø§Ù„ØªØ´ØºÙŠÙ„ =====
if __name__ == "__main__":
    init_db()
    logging.info("ðŸ¤– Bot starting...")
    app.run()
