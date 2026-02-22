import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters

# إعدادات البيئة
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

ADMIN_CHANNEL = -1003547072209

app = Client("test_import_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=4)

# دالة مساعدة للاتصال بقاعدة البيانات
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

# ======= الأمر /import_updated =======
@app.on_message(filters.command("import_updated") & filters.private)
async def import_updated_series(client, message):

    await message.reply_text("بدأ الاختبار... التحقق من وجود رسائل في القناة")

    count = 0

    async for msg in client.get_chat_history(ADMIN_CHANNEL, limit=10):  # تجربة أول 10 فقط
        if not (msg.video or (msg.document and msg.document.mime_type.startswith("video"))):
            continue
        caption = (msg.caption or "").strip()
        if not caption:
            continue
        await message.reply_text(f"تم العثور على فيديو: {msg.id}، الوصف: {caption}")
        count += 1

    await message.reply_text(f"تم فحص {count} رسالة فيديو في القناة ✅")

# ======= تشغيل البوت =======
if __name__ == "__main__":
    app.run()
