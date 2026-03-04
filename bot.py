import os
import psycopg2
import logging
import re
from html import escape
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from pyrogram.enums import ParseMode

# ===== الإعدادات =====
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_ID = 7720165591

SOURCE_CHANNEL = "-1003547072209"
PUBLIC_POST_CHANNEL = "-1003554018307" 
FORCE_SUB_CHANNEL = "-1003894735143" 
FORCE_SUB_LINK = "https://t.me/+7AC_HNR8QFI5OWY0"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== قاعدة البيانات (إضافة عمود post_id إذا لم يوجد) =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            conn.commit()
            result = None
        cur.close()
        conn.close()
        return result
    except Exception as e:
        logging.error(f"❌ Database Error: {e}")
        return None

# دالة التنسيق (التشفير بالنقاط)
def obfuscate_visual(text):
    if not text: return ""
    return " . ".join(list(text.replace(" ", "  ")))

async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except: return True 

MAIN_MENU = ReplyKeyboardMarkup([[KeyboardButton("🔍 كيف أبحث عن مسلسل؟")], [KeyboardButton("✍️ طلب مسلسل جديد")]], resize_keyboard=True)

# ===== [مهم] نظام التعديل التلقائي في القناة =====
@app.on_edited_message(filters.chat(int(SOURCE_CHANNEL)) & filters.photo)
async def handle_edit(client, message):
    new_title = message.caption or "مسلسل"
    # البحث عن الفيديو المرتبط بهذا البوستر
    res = db_query("SELECT v_id, ep_num, quality, duration, post_id FROM videos WHERE poster_id=%s LIMIT 1", (message.photo.file_id,))
    
    if res:
        v_id, ep, q, dur, post_id = res[0]
        # 1. تحديث قاعدة البيانات بالاسم الجديد
        db_query("UPDATE videos SET title=%s WHERE v_id=%s", (new_title, v_id), fetch=False)
        
        # 2. إذا كان المنشور موجوداً في القناة، قم بتعديله فوراً
        if post_id:
            try:
                safe_title = obfuscate_visual(escape(new_title))
                new_caption = (
                    f"🎬 <b>{safe_title}</b>\n\n"
                    f"<b>الحلقة: [{ep}]</b>\n"
                    f"<b>الجودة: [{q}]</b>\n"
                    f"<b>المدة: [{dur}]</b>\n\n"
                    f"نتمنى لكم مشاهدة ممتعة."
                )
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{(await client.get_me()).username}?start={v_id}")]])
                
                await client.edit_message_caption(
                    chat_id=PUBLIC_POST_CHANNEL,
                    message_id=int(post_id),
                    caption=new_caption,
                    reply_markup=markup
                )
                await message.reply_text(f"✅ تم تحديث المنشور في القناة إلى: {new_title}")
            except Exception as e:
                logging.error(f"Edit error: {e}")

# ===== نظام النشر (حفظ post_id) =====
@app.on_message(filters.chat(int(SOURCE_CHANNEL)) & filters.text & ~filters.command(["start", "stats"]))
async def receive_ep_num(client, message):
    if not message.text.isdigit(): return
    res = db_query("SELECT v_id, title, poster_id, quality, duration FROM videos WHERE status='awaiting_ep' ORDER BY v_id DESC LIMIT 1")
    if not res: return
    v_id, title, p_id, q, dur = res[0]
    ep_num = message.text
    
    me = await client.get_me()
    safe_title = obfuscate_visual(escape(title))
    caption = f"🎬 <b>{safe_title}</b>\n\n<b>الحلقة: [{ep_num}]</b>\n<b>الجودة: [{q}]</b>\n<b>المدة: [{dur}]</b>\n\nنتمنى لكم مشاهدة ممتعة."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{me.username}?start={v_id}")]])
    
    try:
        # النشر وحفظ رقم الرسالة (post_id)
        post = await client.send_photo(chat_id=PUBLIC_POST_CHANNEL, photo=p_id, caption=caption, reply_markup=markup)
        
        # حفظ رقم الحلقة و ID المنشور في قاعدة البيانات
        db_query("UPDATE videos SET ep_num=%s, status='posted', post_id=%s WHERE v_id=%s", (ep_num, post.id, v_id), fetch=False)
        
        await message.reply_text(f"🚀 تم النشر بنجاح باسم: {title}")
    except Exception as e:
        await message.reply_text(f"❌ خطأ في النشر: {e}")

# (بقية الكود الخاص بالبحث والرفع تبقى كما هي في الإصدار السابق...)
# [يجب دمج بقية الدوال من الكود السابق هنا ليعمل البوت كاملاً]
