import logging
import psycopg2
import asyncio
import os
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
# 1. الإعدادات (استخدمت بياناتك الصحيحة)
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

ADMIN_CHANNEL = -1003547072209 
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# تشغيل البوت مع وضع الحماية من التوقف
app = Client("mo_final_fix", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, sleep_threshold=60)

# --- دالات المساعدة (التشفير المخفي) ---
def hide_text(text):
    if not text: return "‌"
    # هذا التشفير يستخدم مسافات غير مرئية للحماية من الحقوق
    return "‌".join(list(text))

def center_style(text):
    spacer = "ㅤ" * 5
    return f"{spacer}{text}{spacer}"

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchone() if fetchone else (cur.fetchall() if fetchall else None)
        if commit: conn.commit()
        cur.close()
        return result
    except Exception as e:
        print(f"DB Error: {e}")
        return None
    finally:
        if conn: conn.close()

# ==============================
# 2. أوامر الإدارة (رفع الحلقات)
# ==============================

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.video | filters.document))
async def on_video(client, message):
    v_id = str(message.id)
    sec = message.video.duration if message.video else getattr(message.document, "duration", 0)
    db_query("INSERT INTO temp_upload (chat_id, v_id, duration, step) VALUES (%s, %s, %s, 'awaiting_poster') ON CONFLICT (chat_id) DO UPDATE SET v_id=EXCLUDED.v_id, step='awaiting_poster'", 
             (message.chat.id, v_id, f"{sec//60}:{sec%60:02d}"), commit=True)
    await message.reply_text("✅ استلمت الفيديو.. أرسل البوستر الآن واكتب اسم المسلسل في الوصف.")

@app.on_message(filters.chat(ADMIN_CHANNEL) & (filters.photo | filters.document))
async def on_poster(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != 'awaiting_poster': return
    if not message.caption:
        return await message.reply_text("⚠️ يا محمد، اكتب اسم المسلسل في وصف الصورة.")
    
    f_id = message.photo.file_id if message.photo else message.document.file_id
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", 
             (f_id, message.caption, message.chat.id), commit=True)
    await message.reply_text(f"✅ تم الربط بمسلسل: **{message.caption}**\n🔢 أرسل رقم الحلقة فقط:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start"]))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep": return
    if not message.text.isdigit(): return
    
    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s", (int(message.text), message.chat.id), commit=True)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p", callback_data="q_1080p"), InlineKeyboardButton("720p", callback_data="q_720p")]])
    await message.reply_text(f"🎬 حلقة {message.text} جاهزة.. اختر الجودة للنشر:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    # حفظ البيانات مشفرة
    safe_title = hide_text(data['title'])
    db_query("""INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) 
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE 
                SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality""", 
                (data['v_id'], data['poster_id'], safe_title, data['ep_num'], data['duration'], quality), commit=True)
    
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['v_id']}"
    hidden_cap = f"**{center_style('🎬 ' + safe_title)}**\n**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**\n**{center_style('⚙️ الجودة: ' + quality)}**"
    
    for ch in PUBLIC_CHANNELS:
        try:
            await client.send_photo(ch, photo=data['poster_id'], caption=hidden_cap, 
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مـشـاهـدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر بنجاح.")

# ==============================
# 3. نظام البحث والمشاهدة (بدون ردود مزعجة)
# ==============================

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("🎬 أهلاً بك يا محمد في بوت المشاهدة.\nالقناة الرسمية: @MoAlmohsen")

    param = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (str(param),), fetchone=True)
    
    if data:
        # البحث عن الحلقات المرتبطة بنفس المسلسل
        clean_name = data['title'].replace('‌', '').strip()
        search_name = hide_text(clean_name)
        related = db_query("SELECT v_id, ep_num FROM episodes WHERE title LIKE %s ORDER BY ep_num ASC", (f"%{search_name}%",), fetchall=True)
        
        bot_info = await client.get_me()
        buttons, row = [], []
        if related:
            for ep in related:
                label = f"🔹 {ep['ep_num']}" if str(ep['v_id']) == str(param) else f"{ep['ep_num']}"
                ep_link = f"https://t.me/{bot_info.username}?start={ep['v_id']}"
                row.append(InlineKeyboardButton(label, url=ep_link))
                if len(row) == 5: buttons.append(row); row = []
            if row: buttons.append(row)
        
        buttons.append([InlineKeyboardButton("🍿 مـزيـد مـن الـمـسـلـسـلات", url="https://t.me/MoAlmohsen")])
        
        try:
            await client.copy_message(message.chat.id, ADMIN_CHANNEL, int(data['v_id']), 
                                      caption=f"**{center_style('🎬 ' + data['title'])}**\n**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**", 
                                      reply_markup=InlineKeyboardMarkup(buttons))
        except:
            await message.reply_text("⚠️ خطأ: البوت يحتاج صلاحية الوصول للقناة الخاصة.")
    else:
        # هنا البوت سيظل صامتاً ولن يرسل "لم أجد نتائج" إلا إذا أردت ذلك
        pass

if __name__ == "__main__":
    app.run()
