from telegram.ext import ApplicationBuilder
import config, asyncio
from database import init_db
from handlers import admin, public, user

async def main():
    await init_db()
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()
    # إعداد القنوات
    app.bot_data["PUBLIC_CHANNEL"] = config.PUBLIC_CHANNEL

    # تسجيل الهاندلرز
    admin.register_handlers(app)
    public.register_handlers(app)
    user.register_handlers(app)

    await app.run_polling()

asyncio.run(main())
