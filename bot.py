import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات البوت القديم (تأكد من وضع التوكن الخاص بـ @Ramadan4kTVbot في متغيرات Railway)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# يوزر بوتك الجديد
NEW_BOT_USERNAME = "Bottemo_bot" 

app = Client("OldBotRedirector", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start") & filters.private)
async def redirect_handler(client, message):
    # إذا دخل المستخدم عبر رابط حلقة (مثلاً start=123)
    if len(message.command) > 1:
        v_id = message.command[1]
        new_link = f"https://t.me/{NEW_BOT_USERNAME}?start={v_id}"
        
        text = (
            "⚠️ **عذراً، هذا البوت لم يعد يعمل!**\n\n"
            "لقد انتقلنا إلى بوت جديد أسرع ويدعم جودات أفضل. "
            "اضغط على الزر أدناه لمشاهدة حلقتك فوراً في البوت الجديد."
        )
        
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ اضغط هنا لمشاهدة الحلقة", url=new_link)]
        ])
    else:
        # إذا دخل للبوت بشكل عام
        text = (
            "أهلاً بك يا محمد..\n"
            "هذا البوت (@Ramadan4kTVbot) توقف عن العمل.\n"
            "يرجى الانتقال ومتابعة مسلسلاتك عبر بوتنا الجديد."
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 الانتقال للبوت الجديد", url=f"https://t.me/{NEW_BOT_USERNAME}")]
        ])

    await message.reply_text(text, reply_markup=reply_markup)

print("✅ بوت التحويل يعمل الآن...")
app.run()
