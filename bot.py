import os, psycopg2, logging, re, asyncio, time
from datetime import datetime
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)

# ===== [1] الإعدادات =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591
BACKUP_CHANNEL_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

PUBLIC_CHANNELS = [
    -1003554018307,
    -1003790915936,
    -1003678294148,
    -1003690441303
]

# ===== [2] تعريف app هنا =====
app = Client("railway_final_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== [3] دوال قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

# ===== [4] استخراج رقم الحلقة =====
async def get_episode_number(client, message_id):
    """
    تبحث عن رقم الحلقة في:
    1. الرسالة الحالية (إذا كانت تحتوي على رقم)
    2. الرسائل التالية (خلال 5 رسائل)
    """
    try:
        # جلب الرسالة الحالية
        current_msg = await client.get_messages(SOURCE_CHANNEL, message_id)
        if not current_msg:
            return 0
        
        # البحث في النص الحالي
        current_text = current_msg.caption or current_msg.text or ""
        
        # البحث عن رقم في النص الحالي
        patterns = [
            r'(?:حلقه|حلقة|الحلقة|الحلقه)\s*[:\-\s]*(\d+)',
            r'رقم\s*[:\-\s]*(\d+)',
            r'#(\d+)',
            r'\[(\d+)\]'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, current_text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        # إذا لم نجد في الرسالة الحالية، نبحث في الرسائل التالية
        next_messages = await client.get_messages(
            SOURCE_CHANNEL, 
            [message_id + i for i in range(1, 6)]  # نفحص الـ 5 رسائل التالية
        )
        
        for msg in next_messages:
            if msg and (msg.caption or msg.text):
                text = msg.caption or msg.text
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        return int(match.group(1))
        
        return 0
        
    except Exception as e:
        logging.error(f"خطأ في البحث عن رقم الحلقة: {e}")
        return 0

# ===== [5] أمر استيراد جميع الحلقات =====
@app.on_message(filters.command("import_all") & filters.user(ADMIN_ID))
async def import_all_episodes(client, message):
    msg = await message.reply_text("🔄 جاري جلب جميع الحلقات من قنوات النشر الأربعة...")
    
    stats = {
        'total': 0,
        'new': 0,
        'updated': 0,
        'errors': 0
    }
    
    channel_names = ["القناة 1", "القناة 2", "القناة 3", "القناة 4"]
    
    for idx, channel_id in enumerate(PUBLIC_CHANNELS):
        await msg.edit_text(f"📡 فحص {channel_names[idx]}...")
        
        try:
            # التأكد من أن البوت عضو في القناة
            await client.get_chat(channel_id)
            
            # جلب آخر 1000 رسالة من القناة
            async for post in client.get_chat_history(channel_id, limit=1000):
                if not post.reply_markup:
                    continue
                    
                for row in post.reply_markup.inline_keyboard:
                    for btn in row:
                        if btn.url and "start=" in btn.url:
                            stats['total'] += 1
                            try:
                                v_id = btn.url.split("start=")[1]
                                
                                # جلب بيانات الحلقة من قناة المصدر
                                source_msg = await client.get_messages(SOURCE_CHANNEL, int(v_id))
                                
                                if source_msg and (source_msg.caption or source_msg.text):
                                    raw_text = source_msg.caption or source_msg.text
                                    
                                    # استخراج اسم المسلسل (أول سطر)
                                    title = raw_text.split('\n')[0][:100]
                                    
                                    # استخراج رقم الحلقة باستخدام الدالة الذكية
                                    ep_num = await get_episode_number(client, int(v_id))
                                    
                                    # إدخال في قاعدة البيانات
                                    db_query("""
                                        INSERT INTO videos (v_id, title, ep_num, status) 
                                        VALUES (%s, %s, %s, 'posted')
                                        ON CONFLICT (v_id) DO UPDATE SET 
                                        title = EXCLUDED.title,
                                        ep_num = EXCLUDED.ep_num
                                    """, (v_id, title, ep_num), fetch=False)
                                    
                                    stats['new'] += 1
                                    
                                else:
                                    stats['errors'] += 1
                                    
                            except Exception as e:
                                stats['errors'] += 1
                                logging.error(f"خطأ: {e}")
                                
        except Exception as e:
            await msg.edit_text(f"❌ خطأ في {channel_names[idx]}: {e}")
            continue
    
    # عرض النتائج
    result_text = f"""✅ **تم الانتهاء من الاستيراد**

📊 **الإحصائيات:**
• إجمالي الحلقات المكتشفة: {stats['total']}
• حلقات جديدة: {stats['new']}
• أخطاء: {stats['errors']}
"""
    
    await msg.edit_text(result_text)

# ===== [6] باقي أوامر البوت =====
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    db_query("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (message.from_user.id,), fetch=False)
    if len(message.command) > 1:
        await show_episode(client, message, message.command[1])
    else:
        await message.reply_text("👋 أهلاً بك في بوت المشاهدة")

# ===== [7] دالة show_episode =====
async def show_episode(client, message, v_id):
    try:
        # جلب البيانات من قاعدة البيانات
        db_data = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
        
        if not db_data:
            return await message.reply_text("❌ الحلقة غير موجودة في قاعدة البيانات")
        
        title, ep = db_data[0]
        
        # جلب الحلقات الأخرى
        other_eps = db_query("""
            SELECT ep_num, v_id FROM videos 
            WHERE title = %s AND ep_num > 0 AND v_id != %s
            ORDER BY ep_num ASC
        """, (title, v_id))
        
        # بناء keyboard
        keyboard = []
        if other_eps:
            row = []
            me = await client.get_me()
            for o_ep, o_vid in other_eps:
                row.append(InlineKeyboardButton(
                    str(o_ep), 
                    url=f"https://t.me/{me.username}?start={o_vid}"
                ))
                if len(row) == 5:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔗 القناة الاحتياطية", url=BACKUP_CHANNEL_LINK)])
        
        # إرسال الحلقة
        await client.copy_message(
            message.chat.id,
            SOURCE_CHANNEL,
            int(v_id),
            caption=f"<b>{title} - الحلقة {ep}</b>",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logging.error(f"خطأ: {e}")
        await message.reply_text("⚠️ حدث خطأ")

# ===== [8] تشغيل البوت =====
if __name__ == "__main__":
    print("🚀 تشغيل البوت...")
    app.run()
