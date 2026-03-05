import os
import logging
import re
import asyncio
from html import escape
from psycopg2 import pool
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from pyrogram.enums import ParseMode

# إعداد السجلات
logging.basicConfig(level=logging.INFO)

# ===== 1. تعريف الإعدادات (ستجلب من Railway Variables) =====
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

ADMIN_ID = 7720165591
SOURCE_CHANNEL = -1003547072209
FORCE_SUB_CHANNEL = -1003554018307
FORCE_SUB_LINK = "https://t.me/+PyUeOtPN1fs0NDA0"
PUBLIC_POST_CHANNEL = "@ramadan2206"

# ===== 2. تعريف كائن البوت (APP DEFINITION) =====
app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== 3. قاعدة البيانات =====
try:
    db_pool = pool.SimpleConnectionPool(1, 20, DATABASE_URL, sslmode="require")
except Exception as e:
    logging.error(f"❌ Failed to connect to DB: {e}")

def db_query(query, params=(), fetch=True):
    conn = db_pool.getconn()
    try:
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
        logging.error(f"❌ Database Error: {e}")
        conn.rollback()
        return None
    finally:
        db_pool.putconn(conn)

# ===== 4. الوظائف والأوامر =====

def init_db():
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            quality TEXT DEFAULT 'HD',
            ep_num INTEGER DEFAULT 0,
            duration TEXT DEFAULT '00:00:00',
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            raw_caption TEXT
        )
    """, fetch=False)

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    await message.reply_text(f"أهلاً بك يا محمد {message.from_user.first_name} 👋\nالبوت يعمل الآن بنجاح!")

# باقي الكود الخاص بالأرشفة والبوستر يوضع هنا بالأسفل...

if __name__ == "__main__":
    init_db()
    logging.info("🚀 البوت انطلق...")
    app.run()
