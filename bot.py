import os, psycopg2, logging, re, asyncio, time
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# الإعدادات
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591
SOURCE_CHANNEL = -1003547072209

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else None
        conn.commit()
        return res
    except Exception as e:
        logging.error(f"❌ خطأ قاعدة البيانات: {e}")
        return None
    finally:
        if conn: conn.close()

def init_database():
    # إنشاء الجدول بالهيكلة الصحيحة والمطلوبة في الـ Logs
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            ep_num INTEGER DEFAULT 0,
            video_quality TEXT DEFAULT 'HD',
            duration TEXT DEFAULT '00:00:00',
            poster_id TEXT,
            poster_caption TEXT,
            raw_caption TEXT,
            views INTEGER DEFAULT 0
        )
    """, fetch=False)
    logging.info("✅ تم فحص قاعدة البيانات.")

# --- أوامر الأدمن ---

@app.on_message(filters.command("cleardb") & filters.private)
async def clear_database_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    # حذف الجدول نهائياً
    db_query("DROP TABLE IF EXISTS videos CASCADE", fetch=False)
    # إعادة إنشائه فوراً
    init_database()
    
    await message.reply_text("🗑️ **تم مسح قاعدة البيانات بالكامل وإعادة بنائها بنجاح!**\nيمكنك الآن تشغيل /scan من جديد.")

@app.on_message(filters.command("scan") & filters.private)
async def scan_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    m = await message.reply_text("🔍 جاري الأرشفة (فيديو ← صورة)...")
    
    count = 0
    async for msg in client.get_chat_history(SOURCE_CHANNEL, limit=500):
        if msg.video or msg.document or msg.animation:
            v_id = str(msg.id)
            
            # استخراج البيانات من الفيديو
            raw_cap = msg.caption or ""
            ep_match = re.search(r'(?:الحلقة|حلقة|#)\s*(\d+)', raw_cap, re.I)
            ep = int(ep_match.group(1)) if ep_match else 0
            title = re.sub(r'(?:الحلقة|حلقة|#)\s*\d+.*', '', raw_cap, flags=re.I).strip() or "مسلسل"
            
            media = msg.video or msg.document or msg.animation
            dur = media.duration if hasattr(media, 'duration') and media.duration else 0
            duration = f"{dur//3600:02}:{(dur%3600)//60:02}:{dur%60:02}"
            
            # البحث عن البوستر بعد الفيديو مباشرة
            poster_id, p_cap = None, ""
            for i in range(1, 4):
                try:
                    nxt = await client.get_messages(SOURCE_CHANNEL, msg.id + i)
                    if nxt.photo:
                        poster_id = nxt.photo.file_id
                        p_cap = nxt.caption or ""
                        # تحسين الرقم والعنوان من البوستر
                        if ep == 0:
                            p_ep_match = re.search(r'(?:الحلقة|حلقة|#)\s*(\d+)', p_cap, re.I)
                            ep = int(p_ep_match.group(1)) if p_ep_match else 0
                        if title == "مسلسل" and p_cap:
                            title = re.sub(r'(?:الحلقة|حلقة|#)\s*\d+.*', '', p_cap, flags=re.I).strip()
                        break
                except: continue

            # الحفظ
            db_query("""
                INSERT INTO videos (v_id, title, ep_num, video_quality, duration, poster_id, poster_caption, raw_caption)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, video_quality=EXCLUDED.video_quality
            """, (v_id, title, ep, "HD", duration, poster_id, p_cap, raw_cap), fetch=False)
            count += 1
            await asyncio.sleep(0.4)

    await m.edit_text(f"✅ تم أرشفة {count} حلقة بنجاح!")

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        v_id = str(message.command[1])
        res = db_query("SELECT title, ep_num, video_quality, duration FROM videos WHERE v_id = %s", (v_id,))
        
        if res:
            title, ep, q, dur = res[0]
            cap = f"<b>📺 {title}</b>\n<b>🎞 الحلقة: {ep}</b>\n<b>💿 الجودة: {q}</b>\n<b>⏳ المدة: {dur}</b>"
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=cap)
            db_query("UPDATE videos SET views = views + 1 WHERE v_id = %s", (v_id,), fetch=False)
        else:
            await message.reply_text("❌ الحلقة غير مؤرشفة، أرسل /scan لتحديث قاعدة البيانات.")
    else:
        await message.reply_text(f"مرحباً بك يا محمد! أرسل رابط الحلقة.")

if __name__ == "__main__":
    init_database()
    app.run()
