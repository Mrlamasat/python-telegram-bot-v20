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
API_ID         = int(os.environ.get("API_ID", 0))
API_HASH       = os.environ.get("API_HASH")
SOURCE_CHANNEL = os.environ.get("SOURCE_CHANNEL", "@Ramadan4kTV")

app = Client("mo_userbot", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH, in_memory=True)

def db_query(query, params=(), commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchone() if not commit else None
        if commit: conn.commit()
        cur.close()
        return res
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# -----------------------------
# ▶️ نظام المشاهدة والتحديث التلقائي
# -----------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        v_id = message.command[1]
        
        # 1. محاولة إرسال الحلقة مباشرة من القناة المصدر
        try:
            sent_msg = await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=SOURCE_CHANNEL,
                message_id=int(v_id)
            )
            
            # 2. إذا نجح الإرسال، قم بتحديث قاعدة البيانات فوراً
            title = sent_msg.caption or f"حلقة رقم {v_id}"
            db_query(
                "INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title",
                (v_id, title), commit=True
            )
            print(f"✅ تم إرسال الحلقة {v_id} وتحديث قاعدة البيانات تلقائياً.")
            return

        except Exception as e:
            print(f"Fetch Error: {e}")
            return await message.reply_text("❌ عذراً، لم أتمكن من جلب هذه الحلقة من المصدر حالياً.")

    # الرد الافتراضي
    await message.reply_text("🎬 أهلاً بك يا محمد.\nأرسل اسم المسلسل للبحث عنه أو اضغط على روابط المشاهدة.")

if __name__ == "__main__":
    print("🚀 البوت يعمل الآن بنظام التحديث التلقائي عند المشاهدة...")
    app.run()
