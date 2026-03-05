import os, psycopg2, logging, re, asyncio
from pyrogram import Client, filters

# --- الإعدادات ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591 
SOURCE_CHANNEL = -1003547072209 

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- قاعدة البيانات ---
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

# --- مصفاة العناوين الذكية (الإصدار المطور لعام 2026) ---
def smart_clean_title(text):
    if not text: return "مسلسل"
    
    # 1. قائمة الكلمات الترويجية والتقنية المطلوب حذفها "فقط" وليس حذف السطر كاملاً
    garbage_patterns = [
        r"الجودة\s*[:：]?\s*[^\n]*", 
        r"المدة\s*[:：]?\s*[^\n]*",
        r"سنة العرض\s*[:：]?\s*[^\n]*",
        r"اضغط هنا للمشاهدة",
        r"مشاهدة ممتعة",
        r"دقيقة", r"HD", r"✨", r"⏱", r"📥", r"💿", r"⏳", r"🎞",
        r"http\S+", r"www\S+", r"t\.me\/\S+"
    ]
    
    temp_text = text
    for pattern in garbage_patterns:
        temp_text = re.sub(pattern, "", temp_text, flags=re.I)

    # 2. حذف كلمة (الحلقة/حلقة/EP) وما يتبعها من أرقام
    temp_text = re.sub(r'(?:الحلقة|حلقة|#|EP)\s*\d+.*', '', temp_text, flags=re.I)
    
    # 3. حذف أي أرقام متبقية
    temp_text = re.sub(r'\d+', '', temp_text)
    
    # 4. حذف الرموز والايقونات (إبقاء الحروف العربية والإنجليزية والمسافات)
    temp_text = re.sub(r'[^\s\w\u0600-\u06FF]', '', temp_text)
    
    # 5. تنظيف المسافات الزائدة والأسطر الفارغة
    lines = [line.strip() for line in temp_text.split('\n') if line.strip()]
    final_title = " ".join(lines)
    final_title = re.sub(r'\s+', ' ', final_title).strip()
    
    # إذا فشل الاستخراج، نأخذ أول سطر من النص الأصلي قبل الفلترة العنيفة
    if not final_title or len(final_title) < 2:
        first_line = text.split('\n')[0]
        final_title = re.sub(r'[^\s\w\u0600-\u06FF]', '', first_line).strip()

    return final_title if final_title else "مسلسل"

# --- الأوامر ---

@app.on_message(filters.command("clean_titles") & filters.private)
async def clean_titles_cmd(client, message):
    if message.from_user.id != ADMIN_ID: return
    m = await message.reply_text("🧼 جاري إعادة استخراج الأسماء من الوصف الأصلي بنظام ذكي...")
    
    rows = db_query("SELECT v_id, raw_caption FROM videos")
    updated = 0
    
    for v_id, raw in rows:
        if not raw: continue
        
        new_title = smart_clean_title(raw)
        
        # تحديث العنوان في القاعدة
        db_query("UPDATE videos SET title = %s WHERE v_id = %s", (new_title, v_id), fetch=False)
        updated += 1
            
    await m.edit_text(f"✅ تم الإصلاح!\nتم تحديث **{updated}** عنوان.\nالآن البوت استخرج اسم المسلسل من 'وصف الفيديو' وتخلص من كلمة 'مسلسل' المكررة.")

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if len(message.command) > 1:
        v_id = str(message.command[1])
        res = db_query("SELECT title, ep_num, poster_id FROM videos WHERE v_id = %s", (v_id,))
        if res:
            title, ep, p_id = res[0]
            # هنا نقوم بعرض العنوان النظيف فقط للمستخدم
            caption = f"<b>🎬 {title}</b>\n<b>🎞 الحلقة: {ep}</b>"
            
            if p_id:
                try: await client.send_photo(message.chat.id, p_id, caption=caption)
                except: pass
            
            # إرسال الفيديو بدون الوصف القديم المزعج (نستخدم copy_message مع caption جديدة)
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=SOURCE_CHANNEL,
                message_id=int(v_id),
                caption=f"<b>🎬 {title} - الحلقة {ep}</b>"
            )
        else:
            await message.reply_text("❌ لم يتم العثور على الحلقة.")

if __name__ == "__main__":
    app.run()
