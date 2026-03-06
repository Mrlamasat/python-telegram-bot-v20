import os
import psycopg2
import re
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ===== الإعدادات الأساسية =====
API_ID = 35405228
API_HASH = "dacba460d875d963bbd4462c5eb554d6"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

SOURCE_CHANNEL = -1003547072209
PUBLIC_POST_CHANNEL = -1003554018307
ADMIN_ID = 7720165591  # ✅ تم التعديل للمعرف الصحيح

app = Client("railway_final_stable", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ذاكرة مؤقتة
BOT_CACHE = {"username": None}

# ===== دوال قاعدة البيانات =====
def db_query(query, params=(), fetch=True):
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require", connect_timeout=10)
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchall() if fetch else (conn.commit() or None)
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logging.error(f"Database Error: {e}")
        return []

def init_database():
    """إنشاء جدول قاعدة البيانات إذا لم يكن موجوداً"""
    db_query("""
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            title TEXT,
            poster_id TEXT,
            ep_num INTEGER,
            status TEXT DEFAULT 'waiting',
            views INTEGER DEFAULT 0,
            last_view TIMESTAMP
        )
    """, fetch=False)
    logging.info("✅ قاعدة البيانات جاهزة")

# ===== دوال مساعدة =====
def obfuscate_visual(text):
    if not text: return "مسلسل"
    clean = re.sub(r'[^\w\s]', '', text).replace(" ", "")
    return " . ".join(list(clean))

async def get_bot_username():
    if not BOT_CACHE["username"]:
        me = await app.get_me()
        BOT_CACHE["username"] = me.username
    return BOT_CACHE["username"]

# ===== معالج الأوامر في الخاص =====
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    try:
        if len(message.command) > 1:
            v_id = message.command[1]
            
            # تحديث المشاهدات
            db_query("UPDATE videos SET views = COALESCE(views, 0) + 1, last_view = CURRENT_TIMESTAMP WHERE v_id = %s", (v_id,), fetch=False)
            
            # جلب معلومات الحلقة
            res = db_query("SELECT title, ep_num FROM videos WHERE v_id = %s", (v_id,))
            if not res:
                return await message.reply_text("⚠️ الحلقة غير موجودة.")
            
            title, ep = res[0]
            username = await get_bot_username()
            
            # جلب قائمة الحلقات
            ep_res = db_query("SELECT v_id, ep_num FROM videos WHERE title = %s AND status = 'posted' ORDER BY ep_num ASC", (title,))
            
            # بناء الأزرار
            btns, row, seen = [], [], set()
            for vid, e_n in ep_res:
                if e_n == 0 or e_n in seen:
                    continue
                seen.add(e_n)
                label = f"✅ {e_n}" if str(vid) == str(v_id) else f"{e_n}"
                row.append(InlineKeyboardButton(label, url=f"https://t.me/{username}?start={vid}"))
                if len(row) == 5:
                    btns.append(row)
                    row = []
            if row:
                btns.append(row)
            
            caption = f"<b>📺 {obfuscate_visual(title)} - حلقة {ep}</b>"
            
            try:
                await client.copy_message(
                    message.chat.id,
                    SOURCE_CHANNEL,
                    int(v_id),
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(btns) if btns else None,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                await message.reply_text(f"⚠️ خطأ في جلب الفيديو: {e}")
        else:
            await message.reply_text("👋 أهلاً بك في بوت المسلسلات!\nتابع قناتنا لمشاهدة أحدث الحلقات.")
    except Exception as e:
        logging.error(f"خطأ في start: {e}")
        await message.reply_text("❌ حدث خطأ، حاول مرة أخرى.")

@app.on_message(filters.command("id") & filters.private)
async def id_command(client, message):
    await message.reply_text(f"معرفك: `{message.from_user.id}`")

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    try:
        # التحقق من أن الأمر من المدير
        if message.from_user.id != ADMIN_ID:
            return await message.reply_text("❌ هذا الأمر للمدير فقط.")
        
        # إحصائيات عامة
        total_videos = db_query("SELECT COUNT(*) FROM videos")[0][0]
        total_views = db_query("SELECT SUM(views) FROM videos")[0][0] or 0
        
        text = f"📊 **إحصائيات عامة**\n\n"
        text += f"📹 إجمالي الفيديوهات: {total_videos}\n"
        text += f"👀 إجمالي المشاهدات: {total_views}\n\n"
        text += "**أكثر 5 مسلسلات مشاهدة:**\n"
        
        top_series = db_query("SELECT title, SUM(views) FROM videos GROUP BY title ORDER BY SUM(views) DESC LIMIT 5")
        if top_series:
            for title, views in top_series:
                text += f"• {obfuscate_visual(title)}: {views} مشاهدة\n"
        else:
            text += "لا توجد بيانات كافية\n"
        
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ: {e}")

@app.on_message(filters.command("debug") & filters.private)
async def debug_command(client, message):
    try:
        # التحقق من أن الأمر من المدير
        if message.from_user.id != ADMIN_ID:
            return await message.reply_text("❌ هذا الأمر للمدير فقط.")
        
        text = "🔍 **تشخيص البوت**\n\n"
        
        # 1. معلومات البوت
        me = await client.get_me()
        text += f"**معلومات البوت:**\n"
        text += f"• الاسم: {me.first_name}\n"
        text += f"• اليوزرنيم: @{me.username}\n"
        text += f"• المعرف: {me.id}\n\n"
        
        # 2. معلومات القناة المصدر
        try:
            channel = await client.get_chat(SOURCE_CHANNEL)
            text += f"**قناة المصدر:**\n"
            text += f"• الاسم: {channel.title}\n"
            text += f"• المعرف: {channel.id}\n"
            
            # التحقق من صلاحيات البوت
            bot_member = await client.get_chat_member(SOURCE_CHANNEL, "me")
            text += f"• صلاحية البوت: {bot_member.status}\n"
        except Exception as e:
            text += f"• ❌ خطأ في الوصول للقناة: {e}\n"
        
        text += f"\n"
        
        # 3. معلومات القناة العامة
        try:
            pub_channel = await client.get_chat(PUBLIC_POST_CHANNEL)
            text += f"**القناة العامة:**\n"
            text += f"• الاسم: {pub_channel.title}\n"
            text += f"• المعرف: {pub_channel.id}\n"
            
            # التحقق من وجود البوت
            try:
                bot_member_pub = await client.get_chat_member(PUBLIC_POST_CHANNEL, "me")
                text += f"• صلاحية البوت: {bot_member_pub.status}\n"
            except:
                text += f"• ⚠️ البوت ليس عضواً في القناة\n"
        except Exception as e:
            text += f"• ❌ خطأ في الوصول للقناة: {e}\n"
        
        text += f"\n"
        
        # 4. قاعدة البيانات
        try:
            # عدد الفيديوهات
            count = db_query("SELECT COUNT(*) FROM videos")[0][0]
            text += f"**قاعدة البيانات:**\n"
            text += f"• عدد الفيديوهات: {count}\n"
            
            # آخر 5 فيديوهات
            recent = db_query("""
                SELECT v_id, title, ep_num, status, views 
                FROM videos 
                ORDER BY CAST(v_id AS INTEGER) DESC 
                LIMIT 5
            """)
            
            if recent:
                text += f"\n**آخر 5 فيديوهات:**\n"
                for v_id, title, ep, status, views in recent:
                    text += f"• {v_id}: {title or 'بدون عنوان'} | حلقة {ep or '?'} | {status} | {views} مشاهدة\n"
        except Exception as e:
            text += f"• ❌ خطأ في قاعدة البيانات: {e}\n"
        
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await message.reply_text(f"❌ خطأ في التشخيص: {e}")

# ===== معالج قناة المصدر (لرفع الفيديوهات) =====
@app.on_message(filters.chat(SOURCE_CHANNEL))
async def handle_source(client, message):
    try:
        logging.info(f"📥 رسالة جديدة - ID: {message.id}, Type: {message.media}")
        
        # 1. معالجة الفيديو
        if message.video or message.document:
            v_id = str(message.id)
            # حذف أي بيانات سابقة
            db_query("DELETE FROM videos WHERE v_id = %s", (v_id,), fetch=False)
            db_query("INSERT INTO videos (v_id, status) VALUES (%s, 'waiting')", (v_id,), fetch=False)
            
            await client.send_message(
                SOURCE_CHANNEL,
                "✅ تم استلام الفيديو!\n📌 أرسل الآن البوستر (صورة) مع اسم المسلسل في الوصف:",
                reply_to_message_id=message.id
            )
            logging.info(f"✅ تم تسجيل الفيديو {v_id} في حالة انتظار")
        
        # 2. معالجة البوستر (صورة)
        elif message.photo:
            # البحث عن آخر فيديو في حالة waiting
            res = db_query("SELECT v_id FROM videos WHERE status='waiting' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await client.send_message(
                    SOURCE_CHANNEL,
                    "❌ لا يوجد فيديو في الانتظار. أرسل الفيديو أولاً.",
                    reply_to_message_id=message.id
                )
                return
                
            v_id = res[0][0]
            title = message.caption or "مسلسل رمضان"
            
            db_query(
                "UPDATE videos SET title=%s, poster_id=%s, status='awaiting_ep' WHERE v_id=%s",
                (title, message.photo.file_id, v_id),
                fetch=False
            )
            
            await client.send_message(
                SOURCE_CHANNEL,
                f"📌 تم حفظ البوستر لـ: {title}\n🔢 أرسل الآن رقم الحلقة فقط:",
                reply_to_message_id=message.id
            )
            logging.info(f"✅ تم حفظ بوستر للفيديو {v_id}")
        
        # 3. معالجة رقم الحلقة
        elif message.text and message.text.strip().isdigit():
            res = db_query("SELECT v_id, title, poster_id FROM videos WHERE status='awaiting_ep' ORDER BY CAST(v_id AS INTEGER) DESC LIMIT 1")
            if not res:
                await client.send_message(
                    SOURCE_CHANNEL,
                    "❌ لا يوجد فيديو في انتظار رقم الحلقة.",
                    reply_to_message_id=message.id
                )
                return
            
            v_id, title, p_id = res[0]
            ep_num = int(message.text.strip())
            
            db_query(
                "UPDATE videos SET ep_num=%s, status='posted' WHERE v_id=%s",
                (ep_num, v_id),
                fetch=False
            )
            
            # النشر في القناة العامة
            username = await get_bot_username()
            pub_caption = f"🎬 <b>{obfuscate_visual(title)}</b>\n\n<b>الحلقة: [{ep_num}]</b>"
            pub_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ مشاهدة الحلقة", url=f"https://t.me/{username}?start={v_id}")
            ]])
            
            try:
                await client.send_photo(
                    chat_id=PUBLIC_POST_CHANNEL,
                    photo=p_id,
                    caption=pub_caption,
                    reply_markup=pub_markup,
                    parse_mode=ParseMode.HTML
                )
                
                await client.send_message(
                    SOURCE_CHANNEL,
                    f"✅ تم النشر بنجاح!\n🎬 {title} - حلقة {ep_num}",
                    reply_to_message_id=message.id
                )
                logging.info(f"✅ تم نشر الحلقة {ep_num} من {title}")
                
            except Exception as e:
                await client.send_message(
                    SOURCE_CHANNEL,
                    f"❌ فشل النشر في القناة العامة: {e}",
                    reply_to_message_id=message.id
                )
        
        # 4. رسالة لأي نص آخر
        elif message.text:
            await client.send_message(
                SOURCE_CHANNEL,
                "📝 أرسل فيديو أولاً لبدء عملية الرفع.",
                reply_to_message_id=message.id
            )
    
    except Exception as e:
        logging.error(f"خطأ في معالج القناة: {e}")
        try:
            await client.send_message(
                SOURCE_CHANNEL,
                f"❌ حدث خطأ: {str(e)}"
            )
        except:
            pass

# ===== تشغيل البوت =====
if __name__ == "__main__":
    # تهيئة قاعدة البيانات
    init_database()
    
    # تشغيل البوت
    logging.info("🚀 بدء تشغيل البوت...")
    app.run()
