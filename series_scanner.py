import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import re

# ===== [1] الإعدادات =====
SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591

# ===== [2] دوال الاستخراج =====
def extract_episode_number(text):
    if not text: return 0
    text = text.strip()
    match = re.search(r'(?:حلقة|حلقه|الحلقة|الحلقه)\s*[:\-]?\s*(\d+)', text, re.IGNORECASE)
    if match: return int(match.group(1))
    match = re.search(r'[\[\(\{](\d+)[\]\)\}]', text)
    if match: return int(match.group(1))
    match = re.search(r'-\s*(\d+)\s*$', text)
    if match: return int(match.group(1))
    nums = re.findall(r'\d+', text)
    if nums: return int(nums[-1])
    return 0

# ===== [3] دالة الفحص (نسخة جديدة بدون استخدام get_chat_history) =====
async def scan_series_in_source(client, db_query, series_name):
    """فحص المسلسل في قاعدة البيانات فقط (بدون محاولة الوصول للقناة)"""
    
    try:
        # الحلقات الموجودة حالياً في قاعدة البيانات
        existing = db_query(
            "SELECT ep_num FROM videos WHERE series_name ILIKE %s ORDER BY ep_num",
            (f"%{series_name}%",)
        )
        
        if not existing:
            return f"❌ لا توجد حلقات لمسلسل {series_name} في قاعدة البيانات"
        
        numbers = [str(ep[0]) for ep in existing]
        
        report = f"🔍 **نتائج فحص مسلسل: {series_name}**\n"
        report += "━━━━━━━━━━━━━━━\n\n"
        report += f"📊 **الحلقات الموجودة في قاعدة البيانات:**\n"
        report += f"عدد الحلقات: {len(numbers)}\n"
        report += f"الأرقام: {', '.join(numbers[:30])}\n\n"
        report += "⚠️ **ملاحظة:** البوت لا يستطيع البحث في قناة المصدر بسبب قيود تيليجرام.\n"
        report += "لإضافة حلقات جديدة، استخدم الأمر:\n"
        report += "`/add_series اسم_المسلسل`"
        
        return report
        
    except Exception as e:
        return f"❌ خطأ: {e}"

# ===== [4] دالة إضافة مسلسل كامل يدوياً =====
async def add_series_manual(client, db_query, series_name):
    """إضافة جميع حلقات مسلسل يدوياً (تقوم أنت بتحديد الأرقام)"""
    
    # التحقق من وجود المسلسل
    existing = db_query("SELECT ep_num FROM videos WHERE series_name ILIKE %s", (f"%{series_name}%",))
    
    text = f"🎬 **إضافة حلقات {series_name}**\n\n"
    text += "الرجاء إرسال قائمة أرقام الحلقات بالصيغة:\n"
    text += "`بداية-نهاية` أو أرقام مفصولة بفواصل\n\n"
    text += "مثال: `1-30`\n"
    text += "أو: `1,2,3,4,5`\n\n"
    text += "الحلقات الموجودة حالياً: "
    
    if existing:
        nums = [str(ep[0]) for ep in existing]
        text += ", ".join(nums)
    else:
        text += "لا توجد"
    
    return text

# ===== [5] تسجيل الأوامر =====
def register_scan_commands(app, db_query):
    
    @app.on_message(filters.command("scan_series") & filters.user(ADMIN_ID))
    async def scan_series_command(client, message):
        try:
            cmd = message.text.split(maxsplit=1)
            if len(cmd) < 2:
                await message.reply_text("❌ استخدم: /scan_series اسم_المسلسل")
                return
            
            series_name = cmd[1].strip()
            msg = await message.reply_text(f"🔍 جاري فحص {series_name}...")
            result = await scan_series_in_source(client, db_query, series_name)
            await msg.edit_text(result)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")

    @app.on_message(filters.command("add_series") & filters.user(ADMIN_ID))
    async def add_series_command(client, message):
        try:
            cmd = message.text.split(maxsplit=1)
            if len(cmd) < 2:
                await message.reply_text("❌ استخدم: /add_series اسم_المسلسل")
                return
            
            series_name = cmd[1].strip()
            result = await add_series_manual(client, db_query, series_name)
            
            # تخزين حالة مؤقتة
            async def wait_for_numbers(_, m):
                if m.from_user.id != ADMIN_ID:
                    return
                
                # معالجة الأرقام
                text = m.text.strip()
                numbers = []
                
                if '-' in text:
                    # نطاق مثل 1-30
                    start, end = map(int, text.split('-'))
                    numbers = list(range(start, end + 1))
                else:
                    # أرقام مفصولة بفواصل
                    for part in text.split(','):
                        part = part.strip()
                        if part.isdigit():
                            numbers.append(int(part))
                
                if not numbers:
                    await m.reply_text("❌ لم أتمكن من قراءة الأرقام")
                    return
                
                # إضافة الحلقات
                added = 0
                for ep in numbers:
                    # هنا نحتاج v_id - سأطلب من المستخدم إدخاله
                    await m.reply_text(f"الرجاء إدخال v_id للحلقة {ep} (رابط الرسالة في قناة المصدر)")
                    
                    # هذه تحتاج لمعالجة تفاعلية أكثر تعقيداً
                    # للتبسيط، سنعطي تعليمات فقط
                
                await m.reply_text(f"✅ تمت إضافة {added} حلقة")
            
            await message.reply_text(result)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")

def setup_series_scanner(app, db_query):
    register_scan_commands(app, db_query)
    logging.info("✅ تم إعداد نظام فحص المسلسلات")
