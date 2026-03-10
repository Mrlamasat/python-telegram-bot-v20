import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== [1] الإعدادات =====
SERIES_CHANNEL = -1003894735143
SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591

# ===== [2] متغيرات التخزين =====
fixed_message_id = None
MAX_EPISODES = 30  
user_viewed = {}
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

# ===== [4] بناء الأزرار (توزيع 3 في السطر) =====
def create_series_keyboard(series_list, user_id=None):
    keyboard = []
    row = []
    for item in series_list:
        s_name, count, last_date, max_ep, last_v_id = item
        
        btn_text = s_name
        # فحص حالة الاكتمال
        if s_name in completed_series or max_ep >= MAX_EPISODES:
            btn_text += " ✅"
        else:
            # فحص حالة "جديد" للمستخدم الحالي
            is_new = False
            if last_date:
                if isinstance(last_date, str): last_date = datetime.fromisoformat(last_date)
                if (datetime.now() - last_date).total_seconds() < 86400:
                    if user_id not in user_viewed or s_name not in user_viewed[user_id] or user_viewed[user_id][s_name] < last_date:
                        is_new = True
            if is_new: btn_text += " 🆕"

        row.append(InlineKeyboardButton(btn_text, callback_data=f"v_{last_v_id}"))
        
        # كسر السطر بعد كل 3 أزرار
        if len(row) == 3: 
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return keyboard

# ===== [5] تحديث القائمة الثابتة في القناة =====
async def update_series_channel(client, db_query, force=False):
    global fixed_message_id, last_episode_count, bot_info
    
    res = db_query("SELECT COUNT(*) FROM videos")
    current_count = res[0][0] if res else 0
    
    if not force and current_count <= last_episode_count: return

    if not bot_info:
        bot_info = await client.get_me()

    series_list = get_series_list(db_query)
    if not series_list: return
    
    text = (
        "📺 **قائمة المسلسلات المتاحة**\n"
        "━━━━━━━━━━━━━━\n"
        "🔹 اضغط على المسلسل لمشاهدة الحلقة الأخيرة مباشرة في البوت\n"
        "🔹 العلامة 🆕 تختفي فور ضغطك على المسلسل"
    )
    reply_markup = InlineKeyboardMarkup(create_series_keyboard(series_list))

    try:
        if fixed_message_id:
            await client.edit_message_text(SERIES_CHANNEL, fixed_message_id, text, reply_markup=reply_markup)
        else:
            msg = await client.send_message(SERIES_CHANNEL, text, reply_markup=reply_markup)
            fixed_message_id = msg.id
        last_episode_count = current_count
    except Exception as e:
        logging.error(f"Error in update_menu: {e}")

# 

# ===== [6] معالجات الـ Callback (الضغط على الأزرار) =====
def register_handlers(app, db_query):
    
    @app.on_callback_query(filters.regex(r"^v_"))
    async def handle_view(client, cb):
        v_id = cb.data.replace("v_", "")
        user_id = cb.from_user.id
        
        res = db_query("SELECT series_name FROM videos WHERE v_id = %s", (v_id,))
        if not res:
            return await cb.answer("⚠️ لم يتم العثور على الحلقة!", show_alert=True)
        
        s_name = res[0][0]
        
        # 1. تحديث علامة "جديد" للمستخدم محلياً
        if user_id not in user_viewed: user_viewed[user_id] = {}
        user_viewed[user_id][s_name] = datetime.now()
        
        # 2. تحديث شكل القائمة للمستخدم فوراً لإخفاء 🆕
        series_list = get_series_list(db_query)
        try:
            await cb.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup(create_series_keyboard(series_list, user_id))
            )
        except: pass
        
        # 3. إرسال الفيديو بالنسخ من قناة المصدر
        await cb.answer(f"🍿 جاري إرسال الحلقة...", show_alert=False)
        try:
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=SOURCE_CHANNEL,
                message_id=int(v_id),
                caption=f"🎬 **{s_name}** - أحدث حلقة مضافة"
            )
        except Exception as e:
            logging.error(f"Failed to copy message: {e}")
            await client.send_message(
                user_id,
                f"⚠️ يرجى التأكد من تشغيل البوت أولاً عبر الضغط على /start"
            )

    # معالجات الإدارة (حذف وتغيير حالة المسلسل)
    @app.on_callback_query(filters.regex(r"^del_") & filters.user(ADMIN_ID))
    async def admin_del(client, cb):
        s_name = cb.data.replace("del_", "")
        db_query("DELETE FROM videos WHERE series_name = %s", (s_name,), fetch=False)
        await cb.answer(f"🗑️ تم حذف {s_name}")
        await update_series_channel(client, db_query, force=True)

    @app.on_callback_query(filters.regex(r"^complete_") & filters.user(ADMIN_ID))
    async def admin_complete(client, cb):
        s_name = cb.data.replace("complete_", "")
        completed_series.add(s_name)
        await cb.answer(f"✅ تم تعيين {s_name} كمكتمل")
        await update_series_channel(client, db_query, force=True)

    @app.on_callback_query(filters.regex(r"^uncomplete_") & filters.user(ADMIN_ID))
    async def admin_uncomplete(client, cb):
        s_name = cb.data.replace("uncomplete_", "")
        if s_name in completed_series: completed_series.remove(s_name)
        await cb.answer(f"🔄 تم إلغاء اكتمال {s_name}")
        await update_series_channel(client, db_query, force=True)

# ===== [7] وظائف الربط والإدارة =====
def setup_series_menu(app, db_query):
    register_handlers(app, db_query)
    
    @app.on_message(filters.command("admin_menu") & filters.user(ADMIN_ID))
    async def show_admin(client, message):
        series_list = get_series_list(db_query)
        kb = []
        for s in series_list:
            s_name = s[0]
            kb.append([
                InlineKeyboardButton(f"🗑️ {s_name}", callback_data=f"del_{s_name}"),
                InlineKeyboardButton(
                    f"🔄 إلغاء ✅" if s_name in completed_series else f"✅ مكتمل", 
                    callback_data=f"uncomplete_{s_name}" if s_name in completed_series else f"complete_{s_name}"
                )
            ])
        
        await message.reply(
            "⚙️ **لوحة إدارة القائمة الثابتة**\n\n- الحذف يزيل المسلسل من الرسالة فوراً.\n- 'مكتمل' يضع علامة ✅ بدل 🆕.",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    # تشغيل التحديث الأول
    asyncio.get_event_loop().create_task(update_series_channel(app, db_query, force=True))

async def refresh_series_menu(client, db_query):
    """يتم استدعاء هذه الدالة من الملف الرئيسي عند إضافة حلقة جديدة"""
    await update_series_channel(client, db_query, force=True)
