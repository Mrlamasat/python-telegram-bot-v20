from pyrogram import Client, idle
import asyncio

# ==============================
# 🔐 إعدادات البوت
# ==============================
SESSION_STRING = "BAIcPawAqsz8F_p2JJmXjf2wJeeg2frJbPyA1FfK3gb4urW94P9VCR5N5apDGsEmeJxtehLGkZs7of6guY6fUqlhG3AnvjVKlxCAHA_xja75TxKgIRqUi-GcjFb_JSguFGioFPTIeX5donwup7_TXxfxCqNURpL_4EPenFnqc6EEbOhRa5Wz7rqE7kv-0KznphGohGYovuftOxoZhUAv0ASyD_pYjcyFBn6798_tmUa-LZyluuxY_msjiigO35H0V8gukbedFVezTLBsuoY6iK61mwXHFeFEkczFfOlEXNp-_ZmU4uBSuFqRdaZOLaRAeaXKoX2eWruWCmCY9bq-VErWbe6GTQAAAAHMKGDXAA"
CHANNEL_USERNAME = "@Ramadan4kTV"  # اسم القناة

# إنشاء العميل
app = Client(
    name="bot_session",
    session_string=SESSION_STRING,
    api_id=35405228,
    api_hash="dacba460d875d963bbd4462c5eb554d6",
    in_memory=True
)

# ==============================
# 📥 دالة لسحب الفيديوهات القديمة
# ==============================
async def import_old_videos(limit=5000):
    try:
        print("🔄 بدء سحب الفيديوهات من القناة...")
        count = 0
        async for message in app.get_chat_history(CHANNEL_USERNAME, limit=limit):
            if message.video:
                count += 1
                print(f"🎬 تم العثور على فيديو: {message.id}")
        print(f"✅ انتهى الفحص. تم العثور على {count} فيديو.")
    except Exception as e:
        print(f"⚠️ خطأ أثناء السحب: {e}")

# ==============================
# ▶️ الدالة الرئيسية لتشغيل البوت
# ==============================
async def main():
    print("🚀 البوت بدأ العمل الآن...")
    try:
        # التحقق من إمكانية الوصول للقناة
        chat = await app.get_chat(CHANNEL_USERNAME)
        print(f"✅ البوت يمكنه الوصول للقناة: {chat.title}")
    except Exception as e:
        print(f"❌ لا يمكن الوصول للقناة:\n{e}")
        return

    # سحب الفيديوهات القديمة
    await import_old_videos()

    # إبقاء البوت في وضع الاستعداد للرسائل الجديدة
    print("🤖 البوت الآن في وضع الاستعداد (Idle)...")
    await idle()

# ==============================
# ▶️ تشغيل البوت
# ==============================
if __name__ == "__main__":
    async def runner():
        await app.start()
        await main()
        await app.stop()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        print("⏹️ تم إيقاف البوت باليد.")
