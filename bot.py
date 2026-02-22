import logging
import psycopg2
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ... (الإعدادات الأساسية API_ID, API_HASH, BOT_TOKEN كما هي)

# --- دالة التشفير والتوسيط ---
def format_title(text):
    if not text: return "‌"
    hidden = "‌".join(list(text)) # تشفير لمنع البحث
    spacer = "ㅤ" * 8 # توسيط
    return f"**{spacer}🎬 {hidden}{spacer}**"

# ==============================
# 🛠 أداة تعديل الأوصاف القديمة
# ==============================
@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.command("fix"))
async def fix_old_entry(client, message):
    if len(message.command) < 3:
        return await message.reply_text("⚠️ الطريقة: `/fix [ID] [الاسم الجديد]`\nمثال: `/fix 123 شباب البومب`")
    
    v_id = message.command[1]
    new_name = " ".join(message.command[2:])
    
    # تحديث قاعدة البيانات بالاسم الجديد
    db_query("UPDATE episodes SET title=%s WHERE v_id=%s", (new_name, v_id), commit=True)
    
    await message.reply_text(f"✅ تم تصحيح الوصف للحلقة {v_id} إلى: **{new_name}**\nالآن ستظهر ضمن 'شاهد المزيد' وبتنسيق متوسط.")

# ==============================
# نظام النشر المحدث (توسيط وتشفير)
# ==============================
@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    db_query("""INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) 
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE 
                SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num""", 
                (data['v_id'], data['poster_id'], data['title'], data['ep_num'], data['duration'], quality), commit=True)
    
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['v_id']}"
    
    # النشر بالتنسيق الجديد
    hidden_cap = (
        f"{format_title(data['title'])}\n"
        f"**{'ㅤ'*8}🔢 حلقة رقم: {data['ep_num']}{'ㅤ'*8}**\n"
        f"**{'ㅤ'*8}⚙️ الجودة: {quality}{'ㅤ'*8}**"
    )
    
    for ch in PUBLIC_CHANNELS:
        try:
            await client.send_photo(ch, photo=data['poster_id'], caption=hidden_cap, 
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مـشـاهـدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر بالتنسيق الجديد.")

# ==============================
# نظام العرض (الربط بالاسم)
# ==============================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    param = message.command[1] if len(message.command) > 1 else ""
    if not param: return await message.reply_text("🎬 أهلاً بك.")

    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (param,), fetchone=True)
    if data:
        # الربط بالاسم (يشمل القديم الذي قمت بتصحيحه بـ /fix)
        related = db_query("SELECT v_id, ep_num FROM episodes WHERE title=%s ORDER BY ep_num ASC", (data['title'],), fetchall=True)
        
        bot_info = await client.get_me()
        buttons, row = [], []
        for ep in related:
            label = f"🔹 {ep['ep_num']}" if str(ep['v_id']) == param else f"{ep['ep_num']}"
            row.append(InlineKeyboardButton(label, url=f"https://t.me/{bot_info.username}?start={ep['v_id']}"))
            if len(row) == 5: buttons.append(row); row = []
        if row: buttons.append(row)
        
        buttons.append([InlineKeyboardButton("🍿 شـاهـد الـمـزيد مـن الـحـلـقـات", url=f"https://t.me/{PUBLIC_CHANNELS[0].replace('@','')} ")])

        final_cap = f"{format_title(data['title'])}\n**{'ㅤ'*8}🔢 حلقة رقم: {data['ep_num']}{'ㅤ'*8}**"
        
        try:
            peer = int(ADMIN_CHANNEL) if str(ADMIN_CHANNEL).replace("-", "").isdigit() else ADMIN_CHANNEL
            await client.copy_message(message.chat.id, peer, int(data['v_id']), caption=final_cap, reply_markup=InlineKeyboardMarkup(buttons))
        except: pass
