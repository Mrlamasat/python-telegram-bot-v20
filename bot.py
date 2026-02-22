# bot.py
from pyrogram import Client, idle

# ==============================
# 🔐 Session String جاهز
# ==============================
SESSION_STRING = "BAIcPawAqsz8F_p2JJmXjf2wJeeg2frJbPyA1FfK3gb4urW94P9VCR5N5apDGsEmeJxtehLGkZs7of6guY6fUqlhG3AnvjVKlxCAHA_xja75TxKgIRqUi-GcjFb_JSguFGioFPTIeX5donwup7_TXxfxCqNURpL_4EPenFnqc6EEbOhRa5Wz7rqE7kv-0KznphGohGYovuftOxoZhUAv0ASyD_pYjcyFBn6798_tmUa-LZyluuxY_msjiigO35H0V8gukbedFVezTLBsuoY6iK61mwXHFeFEkczFfOlEXNp-_ZmU4uBSuFqRdaZOLaRAeaXKoX2eWruWCmCY9bq-VErWbe6GTQAAAAHMKGDXAA"

# ==============================
# 📢 ID القناة
# ==============================
ADMIN_CHANNEL = -1003547072209

# ==============================
# ⚙️ إعداد العميل
# ==============================
app = Client(
    name="my_session",
    session_string=SESSION_STRING,
    api_id=35405228,
    api_hash="dacba460d875d963bbd4462c5eb554d6"
)

# ==============================
# 📥 استيراد الفيديوهات القديمة
# ==============================
async def import_old_videos():
    try:
        print("🔄 بدء سحب الفيديوهات من القناة...")

        async for message in app.get_chat_history(ADMIN_CHANNEL):
            if message.video:
                print(f"🎬 تم العثور على فيديو: {message.id}")

        print("✅ انتهى الفحص.")
    except Exception as e:
        print(f"⚠️ خطأ أثناء السحب: {e}")

# ==============================
# ▶️ دالة التشغيل الرئيسية
# ==============================
async def main():
    print("🚀 البوت بدأ العمل الآن...")

    # التحقق من القناة
    try:
        chat = await app.get_chat(ADMIN_CHANNEL)
        print(f"✅ الوصول للقناة: {chat.title}")
    except Exception as e:
        print(f"❌ لا يمكن الوصول للقناة:\n{e}")
        return

    # تنفيذ عملية سحب الحلقات القديمة
    await import_old_videos()

    print("🤖 البوت الآن في وضع الاستعداد...")

# ==============================
# ▶️ تشغيل البوت بطريقة صحيحة
# ==============================
if __name__ == "__main__":
    app.run(main())
