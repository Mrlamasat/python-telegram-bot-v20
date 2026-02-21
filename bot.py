import asyncio
from pyrogram.errors import FloodWait

async def main():
    async with app:
        print("✅ البوت يعمل الآن وبانتظار الملفات...")
        await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        app.run()
    except FloodWait as e:
        print(f"⚠️ حظر مؤقت من تليجرام! يجب الانتظار {e.value} ثانية.")
        # سيقوم البوت هنا بالانتظار تلقائياً إذا أردت، أو يتوقف
