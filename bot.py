import os
from pyrogram import Client, filters

# قراءة المتغيرات من البيئة مباشرة
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ.get("SESSION_STRING")  # اختياري للبوتات الخاصة

# إنشاء تطبيق Pyrogram
app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    session_string=SESSION_STRING
)

# مثال أمر بسيط
@app.on_message(filters.command("start"))
def start(client, message):
    message.reply_text("أهلاً! البوت يعمل الآن ✅")

# حلقة إعادة التشغيل التلقائي عند أي خطأ
while True:
    try:
        print("🚀 بدء تشغيل البوت...")
        app.run()
    except Exception as e:
        print(f"⚠️ حدث خطأ: {e}\nسيتم إعادة التشغيل خلال 5 ثوانٍ...")
        import time
        time.sleep(5)
