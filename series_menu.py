import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003894735143  # قناة عرض المسلسلات (نفسها)
ADMIN_ID = 7720165591

# ===== [2] متغيرات التخزين =====
fixed_message_id = None
MAX_EPISODES = 30  
user_viewed = {}  # لتخزين من شاهد ماذا
completed_series = set()  
last_episode_count = 0
bot_info = None 

# ===== [3] جلب البيانات من قاعدة البيانات =====
def get_series_list(db_query):
    return db_query("""
        SELECT 
            s.series_name,
            COUNT(*) as episode_count,
            MAX(s.created_at) as last_episode_date,
            MAX(s.ep_num) as max_episode,
            (SELECT v_id FROM videos WHERE series_name = s.series_name ORDER BY ep_num DESC LIMIT 1) as last_v_id
        FROM videos s
        WHERE s.series_name IS NOT NULL AND s.series_name != ''
        GROUP BY s.series_name
        ORDER BY s.series_name
    """)

# ===== [4] بناء الأزرار الذكية =====
def create_series_keyboard(series_list, bot_username):
    keyboard = []
    row = []
    for item in series_list:
        s_name, count, last_date, max_ep, last_v_id = item
        
        btn_text = s_name
        
        # ✅ وسم المسلسلات المكتملة
        if s_name in completed_series or max_ep >= MAX_EPISODES:
            btn_text += " ✅"
        else:
            # 🔥 وسم النار للحلقات الجديدة (آخر 24 ساعة)
            if last_date:
                if isinstance(last_date, str): 
                    try:
                        last_date = datetime.fromisoformat(last_date)
                    except:
                        last_date = datetime.now()
                if (datetime.now() - last_date).total_seconds() < 86400:
                    btn_text += " 🔥"

        # الرابط المباشر للبوت الجديد
        direct_url = f"https://t.me/{bot_username}?start={last_v_id}"
        row.append(InlineKeyboardButton(btn_text, url=direct_url))
        
        if len(row) == 3: 
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return keyboard

# ===== [5] التحديث التلقائي للقناة بالنص الجديد =====
async def update_series_channel(client, db_query, force=False):
    global fixed_message_id, last_episode_count, bot_info
    
    res = db_query("SELECT COUNT(*) FROM videos")
    current_count = res[0][0] if res else 0
    if not force and current_count <= last_episode_count: 
        print(f"📊 لا يوجد تحديث جديد (العدد: {current_count})")
        return

    if not bot_info:
        bot_info = await client.get_me()
        print(f"🤖 معلومات البوت: {bot_info.username}")

    series_list = get_series_list(db_query)
    if not series_list:
        print("⚠️ لا توجد مسلسلات في قاعدة البيانات")
        return
    
    # تحديث عدد الحلقات المكتملة تلقائياً
    for item in series_list:
        s_name, count, last_date, max_ep, last_v_id = item
        if max_ep >= MAX_EPISODES:
            completed_series.add(s_name)
    
    text = (
        "🎬 **مكتبة المسلسلات الحصرية**\n"
        "━━━━━━━━━━━━━━━\n"
        "اضغط على اسم المسلسل للمشاهدة الفورية 👇\n\n"
        "✅ **تعني: تم اكتمال المسلسل (الحلقة الأخيرة)**\n"
        "🔥 **تعني: توجد حلقة جديدة مضافة الآن**"
    )

    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list, bot_info.username))

    try:
        if fixed_message_id:
            await client.edit_message_text(SERIES_CHANNEL, fixed_message_id, text, reply_markup=reply_markup)
            print(f"✅ تم تحديث القائمة بنجاح (العدد: {current_count})")
        else:
            # البحث عن رسالة سابقة للبوت في القناة
            async for msg in client.get_chat_history(SERIES_CHANNEL, limit=10):
                if msg.from_user and msg.from_user.is_self:
                    fixed_message_id = msg.id
                    await client.edit_message_text(SERIES_CHANNEL, fixed_message_id, text, reply_markup=reply_markup)
                    print(f"✅ تم العثور على رسالة سابقة وتحديثها (ID: {fixed_message_id})")
                    break
            else:
                # إذا لم يجد رسالة، يرسل رسالة جديدة
                msg = await client.send_message(SERIES_CHANNEL, text, reply_markup=reply_markup)
                fixed_message_id = msg.id
                print(f"✅ تم إرسال رسالة جديدة (ID: {fixed_message_id})")
                
        last_episode_count = current_count
    except Exception as e:
        logging.error(f"خطأ في تحديث القائمة: {e}")
        print(f"❌ خطأ في تحديث القائمة: {e}")

# ===== [6] معالجة الأوامر الجديدة لتجنب التضارب =====
def register_handlers(app, db_query):
    
    # معالجة رابط التشغيل المباشر
    @app.on_message(filters.command("start") & filters.private)
    async def track_start(client, message):
        if len(message.command) > 1:
            v_id = message.command[1]
            res = db_query("SELECT series_name FROM videos WHERE v_id = %s", (v_id,))
            if res:
                s_name = res[0][0]
                user_id = message.from_user.id
                if user_id not in user_viewed: 
                    user_viewed[user_id] = {}
                user_viewed[user_id][s_name] = datetime.now()

    # 🆕 أمر التحديث السريع
    @app.on_message(filters.command("up_menu") & filters.user(ADMIN_ID))
    async def update_series_command(client, message):
        await message.reply_text("🔄 جاري تحديث قائمة القناة...")
        await update_series_channel(client, db_query, force=True)
        await message.reply_text("✅ تم تحديث قائمة المسلسلات في القناة")

    # 🆕 أمر إعادة إنشاء القائمة
    @app.on_message(filters.command("reset_menu") & filters.user(ADMIN_ID))
    async def refresh_series_command(client, message):
        global fixed_message_id
        fixed_message_id = None  
        await message.reply_text("🔄 جاري إعادة إرسال القائمة...")
        await update_series_channel(client, db_query, force=True)
        await message.reply_text("✅ تم إعادة إنشاء قائمة المسلسلات")

    # 🆕 أمر إضافة مسلسل للمكتملة
    @app.on_message(filters.command("complete") & filters.user(ADMIN_ID))
    async def complete_series_command(client, message):
        try:
            command_parts = message.text.split(maxsplit=1)
            if len(command_parts) < 2:
                await message.reply_text("❌ استخدم: /complete اسم_المسلسل")
                return
            
            series_name = command_parts[1].strip()
            completed_series.add(series_name)
            await message.reply_text(f"✅ تم تعيين {series_name} كمسلسل مكتمل")
            await update_series_channel(client, db_query, force=True)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")

    # 🆕 أمر إزالة مسلسل من المكتملة
    @app.on_message(filters.command("incomplete") & filters.user(ADMIN_ID))
    async def incomplete_series_command(client, message):
        try:
            command_parts = message.text.split(maxsplit=1)
            if len(command_parts) < 2:
                await message.reply_text("❌ استخدم: /incomplete اسم_المسلسل")
                return
            
            series_name = command_parts[1].strip()
            if series_name in completed_series:
                completed_series.remove(series_name)
                await message.reply_text(f"✅ تم إزالة {series_name} من قائمة المسلسلات المكتملة")
            else:
                await message.reply_text(f"❌ {series_name} ليس في قائمة المسلسلات المكتملة")
            
            await update_series_channel(client, db_query, force=True)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")

    # 🆕 عرض قائمة المسلسلات المكتملة
    @app.on_message(filters.command("completed_list") & filters.user(ADMIN_ID))
    async def completed_list_command(client, message):
        if not completed_series:
            await message.reply_text("📭 لا توجد مسلسلات مكتملة")
            return
        
        text = "✅ **قائمة المسلسلات المكتملة:**\n\n"
        for series in sorted(completed_series):
            text += f"• {series}\n"
        
        await message.reply_text(text)

    # لوحة الإدارة
    @app.on_message(filters.command("admin_menu") & filters.user(ADMIN_ID))
    async def show_admin(client, message):
        series_list = get_series_list(db_query)
        if not series_list:
            await message.reply_text("📭 لا توجد مسلسلات في قاعدة البيانات")
            return
            
        kb = []
        for item in series_list[:10]:  # نعرض أول 10 فقط لتجنب طول الكيبورد
            s_name = item[0]
            status = "✅" if s_name in completed_series else "⏳"
            kb.append([
                InlineKeyboardButton(f"{status} {s_name}", callback_data=f"select_{s_name}"),
                InlineKeyboardButton(f"🗑️", callback_data=f"del_{s_name}"),
                InlineKeyboardButton(f"✅", callback_data=f"complete_{s_name}")
            ])
        
        if len(series_list) > 10:
            kb.append([InlineKeyboardButton("📋 عرض الكل في القناة", url="https://t.me/series_channel")])
        
        await message.reply_text(
            "⚙️ **لوحة إدارة المسلسلات**\n"
            "اختر مسلسل للتحكم:\n"
            "✅ = مكتمل | 🗑️ = حذف | ✅ = تعيين مكتمل",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    @app.on_callback_query(filters.regex(r"^(del_|complete_|select_)") & filters.user(ADMIN_ID))
    async def handle_admin_actions(client, cb):
        try:
            if cb.data.startswith("del_"):
                s_name = cb.data.replace("del_", "")
                # حذف المسلسل من قاعدة البيانات
                videos = db_query("SELECT v_id FROM videos WHERE series_name = %s", (s_name,))
                count = len(videos) if videos else 0
                
                db_query("DELETE FROM videos WHERE series_name = %s", (s_name,), fetch=False)
                
                if s_name in completed_series:
                    completed_series.remove(s_name)
                    
                await cb.answer(f"🗑️ تم حذف {s_name} ({count} حلقة)")
                
            elif cb.data.startswith("complete_"):
                s_name = cb.data.replace("complete_", "")
                completed_series.add(s_name)
                await cb.answer(f"✅ تم تعيين {s_name} كمنتهي")
                
            elif cb.data.startswith("select_"):
                s_name = cb.data.replace("select_", "")
                # عرض معلومات المسلسل
                videos = db_query("SELECT COUNT(*), MAX(ep_num), SUM(views) FROM videos WHERE series_name = %s", (s_name,))
                count, max_ep, views = videos[0] if videos else (0, 0, 0)
                
                status = "مكتمل ✅" if s_name in completed_series else "جاري ⏳"
                
                text = f"📊 **معلومات {s_name}**\n\n"
                text += f"📌 الحالة: {status}\n"
                text += f"🔢 عدد الحلقات: {count}\n"
                text += f"📺 آخر حلقة: {max_ep}\n"
                text += f"👁️ إجمالي المشاهدات: {views}\n"
                
                # أزرار التحكم
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑️ حذف المسلسل", callback_data=f"del_{s_name}")],
                    [InlineKeyboardButton("✅ تعيين مكتمل", callback_data=f"complete_{s_name}")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_admin")]
                ])
                
                await cb.message.edit_text(text, reply_markup=kb)
                return
            
            # تحديث القائمة بعد أي تغيير
            await update_series_channel(client, db_query, force=True)
            
            # العودة للوحة الرئيسية
            await show_admin(client, cb.message)
            
        except Exception as e:
            logging.error(f"خطأ في معالجة الإجراء: {e}")
            await cb.answer(f"❌ حدث خطأ: {str(e)[:20]}")

    @app.on_callback_query(filters.regex("^back_to_admin$") & filters.user(ADMIN_ID))
    async def back_to_admin(client, cb):
        await show_admin(client, cb.message)

# ===== [7] وظائف الربط والاستدعاء =====
def setup_series_menu(app, db_query):
    register_handlers(app, db_query)
    # تشغيل التحديث الأول بعد 3 ثواني
    asyncio.get_event_loop().create_task(delayed_update(app, db_query))

async def delayed_update(client, db_query):
    """تأخير التحديث الأول لضمان اتصال البوت"""
    await asyncio.sleep(3)
    await update_series_channel(client, db_query, force=True)

async def refresh_series_menu(client, db_query):
    """دالة للتحديث الفوري من الملف الرئيسي"""
    await update_series_channel(client, db_query, force=True)

# ===== [8] أمر للتحقق من حالة القناة =====
def add_channel_check(app):
    @app.on_message(filters.command("check_series_channel") & filters.user(ADMIN_ID))
    async def check_series_channel(client, message):
        try:
            channel = await client.get_chat(SERIES_CHANNEL)
            
            try:
                bot_member = await client.get_chat_member(SERIES_CHANNEL, "me")
                bot_status = bot_member.status
            except:
                bot_status = "❌ ليس عضواً"
            
            text = f"📊 **معلومات قناة المسلسلات**\n\n"
            text += f"اسم القناة: {channel.title}\n"
            text += f"معرف القناة: `{SERIES_CHANNEL}`\n"
            text += f"حالة البوت: {bot_status}\n"
            text += f"الرسالة المثبتة: {fixed_message_id or 'لا توجد'}\n"
            text += f"عدد المسلسلات: {len(get_series_list(db_query))}\n"
            text += f"المسلسلات المكتملة: {len(completed_series)}\n\n"
            
            if bot_status == "administrator":
                text += "✅ البوت مشرف - يمكنه التحديث"
            else:
                text += "❌ البوت ليس مشرفاً - أضفه كمشرف في القناة"
            
            await message.reply_text(text)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ في فحص القناة: {e}")

# إضافة أمر الفحص
add_channel_check(app)  # سيتم استدعاؤها بعد تعريف app
