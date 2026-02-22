import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 1️⃣ الإعدادات من متغيرات البيئة
# ==============================
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
ADMIN_CHANNEL  = int(os.environ.get("ADMIN_CHANNEL", 0))
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")
BOT_TOKEN      = os.environ.get("BOT_TOKEN")

if not all([SESSION_STRING, DATABASE_URL, ADMIN_CHANNEL, PUBLIC_CHANNELS, API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("❌ أحد متغيرات البيئة مفقود. تحقق من SESSION_STRING, DATABASE_URL, ADMIN_CHANNEL, PUBLIC_CHANNELS, API_ID, API_HASH, BOT_TOKEN.")

# ==============================
# 2️⃣ تشغيل الحساب كـ Userbot + Bot
# ==============================
app = Client(
    "ramadan_bot",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=20
)

# ==============================
# 3️⃣ دوال مساعدة
# ==============================
def hide_text(text):
    return "‌".join(list(text)) if text else "‌"

def center_style(text):
    spacer = "ㅤ" * 8
    return f"{spacer}{text}{spacer}"

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
# 4️⃣ سحب الحلقات الجديدة تلقائيًا
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def handle_new_video(client, message):
    v_id = str(message.id)
    duration = message.video.duration if message.video else getattr(message.document, "duration", 0)
    title = message.caption or f"فيديو {v_id}"
    poster_id = message.video.file_id if message.video else getattr(message.document, "file_id", None)
    
    db_query("""INSERT INTO episodes (v_id, title, poster_id, duration) 
                VALUES (%s, %s, %s, %s) 
                ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title, poster_id=EXCLUDED.poster_id""",
             (v_id, title, poster_id, duration), commit=True)
    print(f"📥 تم حفظ الحلقة {v_id}: {title}")

# ==============================
# 5️⃣ تحديث التعديلات على الحلقات
# ==============================
@app.on_edited_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def handle_edit(client, message):
    v_id = str(message.id)
    title = message.caption or f"فيديو {v_id}"
    db_query("UPDATE episodes SET title=%s WHERE v_id=%s", (title, v_id), commit=True)
    print(f"🔄 تم تحديث الحلقة {v_id}: {title}")

# ==============================
# 6️⃣ نظام البحث الصامت
# ==============================
@app.on_message(filters.private & filters.text & ~filters.me & ~filters.outgoing)
async def search_bot(client, message):
    txt = message.text.strip()
    if len(txt) < 2: return
    
    search_query = f"%{txt}%"
    results = db_query("SELECT v_id, title FROM episodes WHERE title ILIKE %s LIMIT 5", (search_query,), fetchall=True)
    
    if results:
        for res in results:
            try:
                await app.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=ADMIN_CHANNEL,
                    message_id=int(res['v_id'])
                )
                await asyncio.sleep(1)
            except: pass

# ==============================
# 7️⃣ زر “مشاهدة الحلقة” يعمل مع ?start=
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("🎬 أهلاً بك.\nتفضل بزيارة قناتنا: @MoAlmohsen")
    
    v_id = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
    if not data:
        return await message.reply_text("❌ الحلقة غير موجودة.")
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    
    caption = f"**{center_style('🎬 ' + hide_text(data['title']))}**\n"
    caption += f"**{center_style('🔢 حلقة رقم: ' + str(data.get('ep_num', '')))}**"
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("▶ مشاهدة الحلقة", url=link)]])
    
    await client.copy_message(
        chat_id=message.chat.id,
        from_chat_id=ADMIN_CHANNEL,
        message_id=int(v_id),
        caption=caption,
        reply_markup=keyboard
    )

# ==============================
# 8️⃣ النشر التلقائي للقنوات العامة
# ==============================
async def publish_to_channels(v_id, title, poster_id, ep_num=None):
    bot_info = await app.get_me()
    link = f"https://t.me/{bot_info.username}?start={v_id}"
    caption = f"**{center_style('🎬 ' + hide_text(title))}**\n"
    if ep_num: caption += f"\n**{center_style('🔢 حلقة رقم: {ep_num}')}**"
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("▶ مشاهدة الحلقة", url=link)]])
    
    for ch in PUBLIC_CHANNELS:
        try:
            await app.send_photo(ch, photo=poster_id, caption=caption, reply_markup=keyboard)
        except Exception as e:
            print(f"❌ خطأ في النشر للقناة {ch}: {e}")

# ==============================
# 9️⃣ تشغيل البوت
# ==============================
if __name__ == "__main__":
    print("🚀 البوت يعمل الآن، جاهز لسحب الحلقات والنشر...")
    app.run()
