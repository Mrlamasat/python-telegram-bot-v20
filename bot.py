import logging
import psycopg2
import asyncio
import os
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ==============================
# 1. الإعدادات الأساسية
# ==============================
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# قناة التخزين (تأكد أن البوت أدمن فيها)
ADMIN_CHANNEL = -1002360567087 
PUBLIC_CHANNELS = ["@RamadanSeries26", "@MoAlmohsen"]

# ==============================
# 2. تعريف البوت وتجهيزه
# ==============================
app = Client("mo_pro_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=20)

# --- دالات المساعدة ---
def hide_text(text):
    """تشفير النص بوضع فواصل مخفية لمنع البحث العالمي"""
    if not text: return "‌"
    return "‌".join(list(text))

def center_style(text):
    """إضافة مسافات شفافة لتوسيط النص"""
    spacer = "ㅤ" * 8
    return f"{spacer}{text}{spacer}"

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require")
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
# 3. أوامر الإدارة (الأدمن)
# ==============================

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.command("fix"))
async def fix_old_entry(client, message):
    if len(message.command) < 3:
        return await message.reply_text("⚠️ الطريقة: `/fix [ID] [الاسم الجديد]`")
    v_id = message.command[1]
    new_name = " ".join(message.command[2:])
    db_query("UPDATE episodes SET title=%s WHERE v_id=%s", (new_name, v_id), commit=True)
    await message.reply_text(f"✅ تم تصحيح الحلقة {v_id} إلى: **{new_name}**")

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
        return await message.reply_text("⚠️ لازم تكتب اسم المسلسل في الوصف.")
    
    f_id = message.photo.file_id if message.photo else message.document.file_id
    db_query("UPDATE temp_upload SET poster_id=%s, title=%s, step='awaiting_ep' WHERE chat_id=%s", 
             (f_id, message.caption, message.chat.id), commit=True)
    await message.reply_text(f"✅ تم الربط باسم: **{message.caption}**\n🔢 الآن أرسل رقم الحلقة فقط:")

@app.on_message(filters.chat(ADMIN_CHANNEL) & filters.text & ~filters.command(["start", "fix"]))
async def on_num(client, message):
    state = db_query("SELECT step FROM temp_upload WHERE chat_id=%s", (message.chat.id,), fetchone=True)
    if not state or state['step'] != "awaiting_ep": return
    if not message.text.isdigit(): return
    
    db_query("UPDATE temp_upload SET ep_num=%s, step='awaiting_quality' WHERE chat_id=%s", (int(message.text), message.chat.id), commit=True)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("1080p", callback_data="q_1080p"), InlineKeyboardButton("720p", callback_data="q_720p")]])
    await message.reply_text(f"🎬 حلقة {message.text}.. اختر الجودة:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^q_"))
async def publish(client, query):
    quality = query.data.split("_")[1]
    data = db_query("SELECT * FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), fetchone=True)
    if not data: return
    
    db_query("""INSERT INTO episodes (v_id, poster_id, title, ep_num, duration, quality) 
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (v_id) DO UPDATE 
                SET title=EXCLUDED.title, ep_num=EXCLUDED.ep_num, quality=EXCLUDED.quality""", 
                (data['v_id'], data['poster_id'], data['title'], data['ep_num'], data['duration'], quality), commit=True)
    
    db_query("DELETE FROM temp_upload WHERE chat_id=%s", (query.message.chat.id,), commit=True)
    bot_info = await client.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['v_id']}"
    
    h_title = hide_text(data['title'])
    hidden_cap = f"**{center_style('🎬 ' + h_title)}**\n**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**\n**{center_style('⚙️ الجودة: ' + quality)}**"
    
    for ch in PUBLIC_CHANNELS:
        try:
            await client.send_photo(ch, photo=data['poster_id'], caption=hidden_cap, 
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مـشـاهـدة الآن", url=link)]]))
        except: pass
    await query.message.edit_text("✅ تم النشر بنجاح.")

# ==============================
# 4. نظام التشغيل (واجهة العضو)
# ==============================

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if len(message.command) < 2:
        return await message.reply_text("🎬 أهلاً بك يا محمد في البوت.\nتفضل بزيارة قناتنا: @MoAlmohsen")

    param = message.command[1]
    data = db_query("SELECT * FROM episodes WHERE v_id=%s", (str(param),), fetchone=True)
    
    if data:
        # البحث عن الحلقات المرتبطة بنفس الاسم (مع تنظيف الاسم)
        clean_name = data['title'].replace('‌', '').strip()
        related = db_query(
            "SELECT v_id, ep_num FROM episodes WHERE title LIKE %s ORDER BY ep_num ASC", 
            (f"%{clean_name}%",), 
            fetchall=True
        )
        
        bot_info = await client.get_me()
        buttons, row = [], []
        
        if related:
            for ep in related:
                label = f"🔹 {ep['ep_num']}" if str(ep['v_id']) == str(param) else f"{ep['ep_num']}"
                # بناء الرابط بشكل آمن لضمان عدم وجود أخطاء BUTTON_URL_INVALID
                ep_link = f"https://t.me/{bot_info.username}?start={ep['v_id']}".replace(" ", "")
                row.append(InlineKeyboardButton(label, url=ep_link))
                if len(row) == 5:
                    buttons.append(row)
                    row = []
            if row: buttons.append(row)
        
        # زر "شاهد المزيد" الثابت والموثوق
        main_url = "https://t.me/MoAlmohsen"
        buttons.append([InlineKeyboardButton("🍿 شـاهـد الـمـزيد مـن الـحـلـقـات", url=main_url)])

        h_title = hide_text(clean_name)
        final_cap = (
            f"**{center_style('🎬 ' + h_title)}**\n"
            f"**{center_style('🔢 حلقة رقم: ' + str(data['ep_num']))}**"
        )
        
        try:
            admin_id = int(str(ADMIN_CHANNEL))
            await client.copy_message(
                chat_id=message.chat.id, 
                from_chat_id=admin_id, 
                message_id=int(data['v_id']), 
                caption=final_cap, 
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            print(f"Error copying: {e}")
            await message.reply_text("⚠️ عذراً، لا يمكنني جلب الفيديو حالياً. تأكد أن البوت مسؤول في قناة التخزين.")
    else:
        await message.reply_text("❌ الحلقة غير موجودة.")

if __name__ == "__main__":
    app.run()
