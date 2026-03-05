import os, psycopg2, logging, re, asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# --- إعدادات البيئة ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591 
SOURCE_CHANNEL = -1003547072209 

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- محرك قاعدة البيانات ---
def db_query(query, params=(), fetch=True):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else None
        conn.commit()
        return res
    except Exception as e:
        logging.error(f"❌ DB ERROR: {e}")
        return None
    finally:
        if conn: conn.close()

# --- مصفاة العناوين الذكية ---
def smart_clean_title(text):
    if not text: return "مفقود ⚠️"
    # حذف نصوص الجودة والروابط والرموز
    garbage = [r"الجودة.*", r"المدة.*", r"سنة العرض.*", r"مشاهدة ممتعة", r"✨", r"⏱", r"HD", r"📥", r"http\S+"]
    temp = text
    for p in garbage: temp = re.sub(p, "", temp, flags=re.I)
    # حذف الحلقة والأرقام والرموز غير العربية/الإنجليزية
    temp = re.sub(r'(?:الحلقة|حلقة|#|EP)\s*\d+.*', '', temp, flags=re.I)
    temp = re.sub(r'\d+', '', temp)
    temp = re.sub(r'[^\s\w\u0600-\u06FF]', '', temp)
    final = re.sub(r'\s+', ' ', temp).strip()
    return final if len(final) > 1 else "مفقود ⚠️"

# --- نظام مراجعة وتعديل العناوين للمشرف ---

@app.on_message(filters.command("check_missing") & filters.private)
async def check_missing(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    # جلب الحلقات التي فشل البوت في تسميتها آلياً
    rows = db_query("SELECT v_id, ep_num, poster_id FROM videos WHERE title = 'مفقود ⚠️' OR title = 'مسلسل' LIMIT 5")
    
    if not rows:
        return await message.reply_text("✅ مذهل! كل العناوين مؤرشفة ومكتملة الأسماء.")
    
    await message.reply_text(f"🔍 وجدنا {len(rows)} حلقات تحتاج لتسمية. جاري عرض المحتوى...")

    for v_id, ep, p_id in rows:
        # 1. إرسال البوستر إن وجد
        if p_id:
            try: await client.send_photo(message.chat.id, p_id, caption=f"🖼 بوستر المعرف: `{v_id}`")
            except: pass
            
        # 2. إرسال الفيديو الأصلي لمعرفة المحتوى
        try:
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id))
        except: pass

        # 3. إرسال زر التعديل
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("تعديل الاسم الآن ✏️", callback_data=f"edit_{v_id}")]])
        await message.reply_text(f"🆔 المعرف: `{v_id}`\n🎞 الحلقة: {ep}\n❓ ما هو اسم هذا المسلسل؟", reply_markup=btn)

@app.on_callback_query(filters.regex(r"^edit_"))
async def cb_edit(client, callback_query):
    v_id = callback_query.data.split("_")[1]
    await callback_query.message.reply_text(
        f"📝 أرسل الاسم الصحيح للمعرف `{v_id}` الآن:",
        reply_markup=ForceReply(selective=True)
    )
    await callback_query.answer()

@app.on_message(filters.reply & filters.private)
async def process_edit(client, message):
    if message.from_user.id != ADMIN_ID: return
    if not message.reply_to_message or "📝" not in message.reply_to_message.text: return
    
    v_id_search = re.search(r'المعرف `(\d+)`', message.reply_to_message.text)
    if v_id_search:
        v_id = v_id_search.group(1)
        new_title = message.text.strip()
        db_query("UPDATE videos SET title = %s WHERE v_id = %s", (new_title, v_id), fetch=False)
        await message.reply_text(f"✅ تم! المعرف `{v_id}` أصبح اسمه: **{new_title}**")

# --- الأوامر الأساسية والأرشفة ---

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        v_id = str(message.command[1])
        res = db_query("SELECT title, ep_num, poster_id FROM videos WHERE v_id = %s", (v_id,))
        if res:
            title, ep, p_id = res[0]
            if p_id:
                try: await client.send_photo(message.chat.id, p_id, caption=f"🎬 {title}\n🎞 الحلقة: {ep}")
                except: pass
            await client.copy_message(message.chat.id, SOURCE_CHANNEL, int(v_id), caption=f"🎬 {title} - الحلقة {ep}")
        else:
            await message.reply_text("❌ لم يتم العثور على الحلقة.")
    else:
        await message.reply_text("👋 أهلاً بك يا محمد! استخدم `/check_missing` لإصلاح العناوين.")

@app.on_message(filters.command("fix_old_data") & filters.private)
async def fix_old_data_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    if len(message.command) < 3: return
    start_id, end_id = int(message.command[1]), int(message.command[2])
    m = await message.reply_text("🚀 بدأت الأرشفة الذكية...")
    count = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            msg = await client.get_messages(SOURCE_CHANNEL, msg_id)
            if msg and (msg.video or msg.document):
                v_title = smart_clean_title(msg.caption)
                # استخراج رقم الحلقة (تبسيطاً نعتمد على الرقم الأخير)
                nums = re.findall(r'\d+', msg.caption or "")
                v_ep = int(nums[-1]) if nums else 0
                
                db_query("""
                    INSERT INTO videos (v_id, title, ep_num, raw_caption)
                    VALUES (%s, %s, %s, %s) ON CONFLICT (v_id) DO NOTHING
                """, (str(msg_id), v_title, v_ep, msg.caption or ""), fetch=False)
                count += 1
            if msg_id % 100 == 0: await m.edit_text(f"⏳ معالجة: {msg_id} | مؤرشف: {count}")
        except: continue
    await m.edit_text(f"✅ اكتملت الأرشفة! تم سحب {count} حلقة.")

@app.on_message(filters.command("clean_titles") & filters.private)
async def clean_titles_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    m = await message.reply_text("🧼 جاري تنظيف العناوين آلياً...")
    rows = db_query("SELECT v_id, raw_caption FROM videos")
    for v_id, raw in rows:
        if raw:
            db_query("UPDATE videos SET title = %s WHERE v_id = %s", (smart_clean_title(raw), v_id), fetch=False)
    await m.edit_text("✅ تم التنظيف الآلي. استخدم الآن `/check_missing` لليدوي.")

if __name__ == "__main__":
    app.run()
