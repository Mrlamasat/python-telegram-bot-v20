import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -----------------------------
# 🔐 الإعدادات
# -----------------------------
SESSION_STRING = os.environ.get("SESSION_STRING")
DATABASE_URL   = os.environ.get("DATABASE_URL")
API_ID         = int(os.environ.get("API_ID"))
API_HASH       = os.environ.get("API_HASH")
# نستخدم اسم القناة أو الـ ID الخاص بها
SOURCE_CHANNEL = os.environ.get("SOURCE_CHANNEL", "@Ramadan4kTV")
PUBLIC_CHANNELS = os.environ.get("PUBLIC_CHANNELS", "").split(",")

app = Client("mo_userbot", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH)

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None)
        if commit: conn.commit()
        cur.close()
        return res
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# جلب الحلقات تلقائياً من القناة المصدرية
@app.on_message(filters.chat(SOURCE_CHANNEL) & filters.video)
async def handle_source_video(client, message):
    v_id = str(message.id)
    title = message.caption or f"فيديو {v_id}"
    db_query(
        "INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title",
        (v_id, title), commit=True
    )
    print(f"📥 تم تخزين حلقة جديدة بمعرف: {v_id}")

# نظام التشغيل عند الضغط على الرابط
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        data = db_query("SELECT * FROM episodes WHERE v_id=%s", (v_id,), fetchone=True)
        
        if data:
            try:
                # محاولة إرسال الفيديو من القناة المصدرية
                await client.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=SOURCE_CHANNEL,
                    message_id=int(v_id),
                    caption=f"**🎬 {data['title']}**"
                )
                return
            except Exception as e:
                print(f"Error: {e}")
                return await message.reply_text("⚠️ فشل جلب الفيديو. تأكد أن البوت عضو في القناة المصدرية.")

    # الرد الافتراضي
    welcome_msg = f"🎬 أهلاً بك يا محمد.\nتفضل بزيارة قناتنا: {PUBLIC_CHANNELS[0] if PUBLIC_CHANNELS else '@MoAlmohsen'}"
    await message.reply_text(welcome_msg)

if __name__ == "__main__":
    app.run()
