from pyrogram import Client
import asyncio

# ==============================
# إعدادات البوت
# ==============================
SESSION_STRING = "BAIcPawAqsz8F_p2JJmXjf2wJeeg2frJbPyA1FfK3gb4urW94P9VCR5N5apDGsEmeJxtehLGkZs7of6guY6fUqlhG3AnvjVKlxCAHA_xja75TxKgIRqUi-GcjFb_JSguFGioFPTIeX5donwup7_TXxfxCqNURpL_4EPenFnqc6EEbOhRa5Wz7rqE7kv-0KznphGohGYovuftOxoZhUAv0ASyD_pYjcyFBn6798_tmUa-LZyluuxY_msjiigO35H0V8gukbedFVezTLBsuoY6iK61mwXHFeFEkczFfOlEXNp-_ZmU4uBSuFqRdaZOLaRAeaXKoX2eWruWCmCY9bq-VErWbe6GTQAAAAHMKGDXAA"
ADMIN_CHANNEL = -1003547072209  # ضع هنا ID القناة الصحيح

app = Client(
    name="check_session",
    session_string=SESSION_STRING,
    api_id=35405228,
    api_hash="dacba460d875d963bbd4462c5eb554d6"
)

async def main():
    await app.start()
    try:
        chat = await app.get_chat(ADMIN_CHANNEL)
        print(f"✅ البوت قادر على الوصول للقناة: {chat.title}")
    except Exception as e:
        print(f"⚠️ خطأ: البوت لا يمكنه الوصول للقناة!\n{e}")
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
