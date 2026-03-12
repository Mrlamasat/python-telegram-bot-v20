import asyncio
import logging
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import SOURCE_CHANNEL, ADMIN_ID
from database import db_query

# ===== دوال الاستخراج (مكررة من bot.py للاستقلالية) =====
def extract_episode_number(text):
    """استخراج رقم الحلقة من النص"""
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

def extract_series_name(text):
    """استخراج اسم المسلسل من النص"""
    if not text: return None
    text = text.strip()
    
    patterns = [
        r'^(.+?)\s+(?:حلقة|حلقه|الحلقة|الحلقه)\s+\d+$',
        r'^(.+?)\s+(\d+)$',
        r'^(.+?)\s*-\s*(\d+)$',
        r'^(.+?)\s*[\[\(\{]\d+[\]\)\}]',
        r'^(.+?)\s+.*?\s+(\d+)$',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'[-\s]+$', '', name)
            name = re.sub(r'[\[\(\{].*$', '', name)
            return name
    
    return text.strip()

# ===== دالة فحص المسلسل في قاعدة البيانات =====
async def scan_series_in_source(client, db_query, series_name):
    """فحص مسلسل في قاعدة البيانات وعرض تقرير عن الحلقات الموجودة"""
    
    try:
        # الحلقات الموجودة حالياً في قاعدة البيانات
        existing_eps = db_query(
            "SELECT ep_num FROM videos WHERE series_name ILIKE %s ORDER BY ep_num",
            (f"%{series_name}%",)
        )
        
        if not existing_eps:
            return f"❌ لا توجد حلقات لمسلسل {series_name} في قاعدة البيانات"
        
        numbers = [str(ep[0]) for ep in existing_eps]
        
        # البحث عن الحلقات المفقودة (افتراضية حتى 30)
        all_possible = set(range(1, 31))
        existing_set = set([int(n) for n in numbers])
        missing = sorted(list(all_possible - existing_set))
        
        report = f"🔍 **نتائج فحص مسلسل: {series_name}**\n"
        report += "━━━━━━━━━━━━━━━\n\n"
        report += f"📊 **الإحصائيات:**\n"
        report += f"✅ حلقات موجودة في قاعدة البيانات: {len(numbers)}\n"
        
        if missing:
            report += f"❓ حلقات مفقودة (يفترض وجودها): {len(missing)}\n"
            report += f"📋 الأرقام المفقودة: {', '.join(map(str, missing[:20]))}"
            if len(missing) > 20:
                report += f" ... و{len(missing)-20} أخرى"
        else:
            report += "✅ جميع الحلقات (1-30) موجودة!\n"
        
        report += "\n\n📋 **الحلقات الموجودة حالياً:**\n"
        report += ", ".join(numbers[:30])
        
        report += "\n\n⚠️ **ملاحظة:** البوت لا يستطيع البحث في قناة المصدر بسبب قيود تيليجرام."
        report += "\nلإضافة حلقات مفقودة، استخدم الأمر:"
        report += f"\n`/add_ep {series_name} رقم_الحلقة v_id`"
        
        return report
        
    except Exception as e:
        return f"❌ خطأ في فحص المسلسل: {e}"

# ===== دالة إضافة حلقة يدوياً =====
async def add_episode_manual(client, db_query, series_name, ep_num, v_id):
    """إضافة حلقة يدوياً إلى قاعدة البيانات"""
    try:
        db_query(
            """INSERT INTO videos (v_id, series_name, ep_num, quality, created_at) 
               VALUES (%s, %s, %s, 'HD', NOW()) 
               ON CONFLICT (v_id) DO UPDATE SET 
               series_name = EXCLUDED.series_name,
               ep_num = EXCLUDED.ep_num""",
            (v_id, series_name, ep_num),
            fetch=False
        )
        return True
    except Exception as e:
        logging.error(f"خطأ في إضافة الحلقة: {e}")
        return False

# ===== دالة إضافة مجموعة حلقات =====
async def add_bulk_episodes(client, db_query, series_name, episodes_data):
    """إضافة مجموعة حلقات دفعة واحدة"""
    added = 0
    failed = 0
    
    for ep_num, v_id in episodes_data:
        try:
            db_query(
                """INSERT INTO videos (v_id, series_name, ep_num, quality, created_at) 
                   VALUES (%s, %s, %s, 'HD', NOW()) 
                   ON CONFLICT (v_id) DO UPDATE SET 
                   series_name = EXCLUDED.series_name,
                   ep_num = EXCLUDED.ep_num""",
                (v_id, series_name, ep_num),
                fetch=False
            )
            added += 1
        except Exception as e:
            failed += 1
            logging.error(f"خطأ في إضافة حلقة {ep_num}: {e}")
    
    return added, failed

# ===== تسجيل أوامر الفحص =====
def register_scan_commands(app, db_query):
    
    @app.on_message(filters.command("scan_series") & filters.user(ADMIN_ID))
    async def scan_series_command(client, message):
        """فحص مسلسل في قاعدة البيانات وعرض تقرير"""
        try:
            command_parts = message.text.split(maxsplit=1)
            if len(command_parts) < 2:
                await message.reply_text("❌ استخدم: /scan_series اسم_المسلسل\nمثال: /scan_series المداح")
                return
            
            series_name = command_parts[1].strip()
            msg = await message.reply_text(f"🔍 جاري فحص مسلسل: {series_name}...")

            result = await scan_series_in_source(client, db_query, series_name)
            
            await msg.edit_text(result)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")

    @app.on_message(filters.command("add_ep") & filters.user(ADMIN_ID))
    async def add_ep_command(client, message):
        """إضافة حلقة يدوياً"""
        try:
            command_parts = message.text.split()
            if len(command_parts) < 4:
                await message.reply_text(
                    "❌ استخدم: /add_ep اسم_المسلسل رقم_الحلقة v_id\n"
                    "مثال: `/add_ep المداح 13 3514`\n\n"
                    "🔍 للحصول على v_id، افتح الحلقة في قناة المصدر:\n"
                    "الرابط: https://t.me/c/3547072209/3514 ← الرقم 3514 هو v_id"
                )
                return
            
            series_name = command_parts[1]
            ep_num = int(command_parts[2])
            v_id = command_parts[3]
            
            success = await add_episode_manual(client, db_query, series_name, ep_num, v_id)
            
            if success:
                await message.reply_text(f"✅ تم إضافة {series_name} - حلقة {ep_num} (ID: {v_id})")
                
                # تحديث قائمة المسلسلات
                try:
                    from series_menu import refresh_series_menu
                    await refresh_series_menu(client)
                except:
                    pass
            else:
                await message.reply_text(f"❌ فشل إضافة الحلقة")
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")

    @app.on_message(filters.command("add_bulk") & filters.user(ADMIN_ID))
    async def add_bulk_command(client, message):
        """إضافة مجموعة حلقات دفعة واحدة"""
        try:
            # تنسيق: /add_bulk اسم_المسلسل 1:3514,2:3515,3:3516
            command_parts = message.text.split(maxsplit=2)
            if len(command_parts) < 3:
                await message.reply_text(
                    "❌ استخدم: /add_bulk اسم_المسلسل البيانات\n"
                    "مثال: `/add_bulk المداح 1:3514,2:3515,3:3516`\n\n"
                    "الصيغة: رقم_الحلقة:v_id مفصولة بفواصل"
                )
                return
            
            series_name = command_parts[1]
            data_str = command_parts[2]
            
            # تحليل البيانات
            episodes_data = []
            parts = data_str.split(',')
            
            for part in parts:
                if ':' in part:
                    ep_str, v_id = part.split(':')
                    try:
                        ep_num = int(ep_str.strip())
                        v_id = v_id.strip()
                        episodes_data.append((ep_num, v_id))
                    except:
                        await message.reply_text(f"❌ خطأ في قراءة: {part}")
                        return
            
            if not episodes_data:
                await message.reply_text("❌ لا توجد بيانات صحيحة")
                return
            
            msg = await message.reply_text(f"🔄 جاري إضافة {len(episodes_data)} حلقة...")
            
            added, failed = await add_bulk_episodes(client, db_query, series_name, episodes_data)
            
            result = f"✅ **نتائج الإضافة**\n\n"
            result += f"✅ تمت الإضافة: {added}\n"
            result += f"❌ فشل: {failed}\n"
            
            if added > 0:
                # تحديث قائمة المسلسلات
                try:
                    from series_menu import refresh_series_menu
                    await refresh_series_menu(client)
                    result += f"\n🔄 تم تحديث قائمة المسلسلات"
                except:
                    pass
            
            await msg.edit_text(result)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")

# ===== دالة التشغيل =====
def setup_series_scanner(app):
    """تشغيل نظام فحص المسلسلات"""
    register_scan_commands(app, db_query)
    logging.info("✅ تم إعداد نظام فحص المسلسلات")
