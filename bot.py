from pyrogram import Client, idle

SESSION_STRING = "BAIcPawAqsz8F_p2JJmXjf2wJeeg2frJbPyA1FfK3gb4urW94P9VCR5N5apDGsEmeJxtehLGkZs7of6guY6fUqlhG3AnvjVKlxCAHA_xja75TxKgIRqUi-GcjFb_JSguFGioFPTIeX5donwup7_TXxfxCqNURpL_4EPenFnqc6EEbOhRa5Wz7rqE7kv-0KznphGohGYovuftOxoZhUAv0ASyD_pYjcyFBn6798_tmUa-LZyluuxY_msjiigO35H0V8gukbedFVezTLBsuoY6iK61mwXHFeFEkczFfOlEXNp-_ZmU4uBSuFqRdaZOLaRAeaXKoX2eWruWCmCY9bq-VErWbe6GTQAAAAHMKGDXAA"
ADMIN_CHANNEL = -1003547072209

app = Client(
    name="my_session",
    session_string=SESSION_STRING,
    api_id=35405228,
    api_hash="dacba460d875d963bbd4462c5eb554d6",
    in_memory=True
)

async def import_old_videos():
    print("🔄 بدء سحب الفيديوهات من القناة...")
    count = 0
    async for message in app.get_chat_history(ADMIN_CHANNEL, limit=5000):
        if message.video:
            count += 1
            print(f"🎬 تم العثور على فيديو: {message.id}")
    print(f"✅ انتهى الفحص. تم العثور على {count} فيديو.")

async def main():
    print("🚀 البوت بدأ العمل الآن...")
    try:
        chat = await app.get_chat(ADMIN_CHANNEL)
        print(f"✅ الوصول للقناة: {chat.title}")
    except Exception as e:
        print(f"❌ لا يمكن الوصول للقناة:\n{e}")
        return

    await import_old_videos()
    print("🤖 البوت الآن في وضع الاستعداد...")
    await idle()  # يبقي البوت مستمرًا

if __name__ == "__main__":
    # ✅ استخدم app.run() فقط لتجنب الخطأ
    app.run(main)
