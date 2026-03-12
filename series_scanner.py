import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ===== [1] الإعدادات =====
SOURCE_CHANNEL = -1003547072209
ADMIN_ID = 7720165591

# ===== [2] دوال الاستخراج (مكررة من الملف الرئيسي) =====
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

# ===== [3] دالة فحص المسلسل في قناة المصدر =====
async def scan_series_in_source(client, db_query, series_name):
    """فحص مسلسل في قناة المصدر وإضافة حلقاته الناقصة"""
    
    try:
        # إرسال إشعار بدء الفحص
        await client.send_message(ADMIN_ID, f"🔍 بدء البحث عن حلقات {series_name} في قناة المصدر...")
        
        # الحلقات الموجودة حالياً في قاعدة البيانات
        existing_eps = db_query(
            "SELECT ep_num FROM videos WHERE series_name = %s ORDER BY ep_num",
            (series_name,)
        )
        existing_numbers = [ep[0] for ep in existing_eps] if existing_eps else []
        
        found_videos = []
        added_count = 0
        skipped_count = 0
        error_count = 0
        
        # فحص آخر 1000 رسالة في القناة
        async for message in client.get_chat_history(SOURCE_CHANNEL, limit=1000):
            if not message.video:
                continue
                
            caption = message.caption or ""
            if series_name.lower() not in caption.lower():
                continue
                
            # استخراج رقم الحلقة
            ep_num = extract_episode_number(caption)
            if ep_num == 0:
                error_count += 1
                continue
                
            v_id = str(message.id)
            found_videos.append((ep_num, v_id, caption[:50]))
            
            # إذا كانت الحلقة غير موجودة، أضفها
            if ep_num not in existing_numbers:
                db_query(
                    """INSERT INTO videos (v_id, series_name, ep_num, quality, created_at) 
                       VALUES (%s, %s, %s, 'HD', %s) 
                       ON CONFLICT (v_id) DO NOTHING""",
                    (v_id, series_name, ep_num, message.date),
                    fetch=False
                )
                added_count += 1
                logging.info(f"➕ تمت إضافة حلقة {ep_num} لمسلسل {series_name}")
            else:
                skipped_count += 1
        
        # ترتيب النتائج
        found_videos.sort(key=lambda x: x[0])
        
        # بناء التقرير
        report = f"🔍 **نتائج فحص مسلسل: {series_name}**\n"
        report += "━━━━━━━━━━━━━━━\n\n"
        report += f"📊 **الإحصائيات:**\n"
        report += f"✅ حلقات موجودة سابقاً: {len(existing_numbers)}\n"
        report += f"➕ حلقات جديدة مضافة: {added_count}\n"
        report += f"⏭️ حلقات مكررة (تم تخطيها): {skipped_count}\n"
        report += f"❌ أخطاء (بدون رقم): {error_count}\n\n"
        
        if added_count > 0:
            report += f"🆕 **الحلقات الجديدة المضافة:**\n"
            new_eps = [f"{ep}" for ep, _, _ in found_videos if ep not in existing_numbers]
            report += ", ".join(map(str, sorted(new_eps)[:20]))
            if len(new_eps) > 20:
                report += f" ... و{len(new_eps)-20} أخرى"
            report += "\n\n"
        
        report += f"📋 **جميع حلقات المسلسل الآن:**\n"
        all_eps = db_query(
            "SELECT ep_num FROM videos WHERE series_name = %s ORDER BY ep_num",
            (series_name,)
        )
        if all_eps:
            all_numbers = [ep[0] for ep in all_eps]
            report += ", ".join(map(str, all_numbers))
        else:
            report += "لا توجد حلقات"
        
        return report
        
    except Exception as e:
        return f"❌ خطأ في فحص المسلسل: {e}"

# ===== [4] دالة تسجيل أوامر الفحص =====
def register_scan_commands(app, db_query):
    
    @app.on_message(filters.command("scan_series") & filters.user(ADMIN_ID))
    async def scan_series_command(client, message):
        """فحص مسلسل في قناة المصدر وإضافة الحلقات الناقصة"""
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

    @app.on_message(filters.command("scan_all") & filters.user(ADMIN_ID))
    async def scan_all_command(client, message):
        """فحص جميع المسلسلات (تحذير: قد يستغرق وقتاً)"""
        msg = await message.reply_text("🔍 جاري فحص جميع المسلسلات... هذا قد يستغرق عدة دقائق")
        
        # جلب جميع المسلسلات من قاعدة البيانات
        all_series = db_query("SELECT DISTINCT series_name FROM videos WHERE series_name IS NOT NULL AND series_name != ''")
        
        total_series = len(all_series)
        scanned = 0
        total_added = 0
        
        report = "📊 **تقرير الفحص الشامل**\n━━━━━━━━━━━━━━━\n\n"
        
        for (series_name,) in all_series:
            scanned += 1
            await msg.edit_text(f"🔄 جاري فحص {series_name}... ({scanned}/{total_series})")
            
            # فحص المسلسل بدون إرسال إشعار
            try:
                existing = db_query("SELECT ep_num FROM videos WHERE series_name = %s", (series_name,))
                existing_nums = [e[0] for e in existing] if existing else []
                
                added = 0
                async for post in client.get_chat_history(SOURCE_CHANNEL, limit=500):
                    if not post.video: continue
                    caption = post.caption or ""
                    if series_name.lower() not in caption.lower(): continue
                    
                    ep = extract_episode_number(caption)
                    if ep and ep not in existing_nums:
                        db_query(
                            "INSERT INTO videos (v_id, series_name, ep_num, quality, created_at) VALUES (%s, %s, %s, 'HD', %s) ON CONFLICT (v_id) DO NOTHING",
                            (str(post.id), series_name, ep, post.date),
                            fetch=False
                        )
                        added += 1
                        total_added += 1
                
                if added > 0:
                    report += f"✅ {series_name}: تمت إضافة {added} حلقة\n"
                else:
                    report += f"ℹ️ {series_name}: لا توجد حلقات جديدة\n"
                    
            except Exception as e:
                report += f"❌ {series_name}: خطأ - {str(e)[:50]}\n"
        
        report += f"\n📊 **الإجمالي:** {total_added} حلقة جديدة مضافة"
        await msg.edit_text(report)

# ===== [5] دالة التشغيل =====
def setup_series_scanner(app, db_query):
    """تشغيل نظام فحص المسلسلات"""
    # استيراد re هنا لأن الدوال تحتاجه
    global re
    import re
    register_scan_commands(app, db_query)
    logging.info("✅ تم إعداد نظام فحص المسلسلات")
