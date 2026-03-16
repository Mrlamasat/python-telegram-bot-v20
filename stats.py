import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_ID
from database import db_query

# ===== [1] إحصائيات عامة =====
def get_general_stats():
    """الحصول على إحصائيات عامة عن البوت"""
    total_videos = db_query("SELECT COUNT(*) FROM videos")[0][0]
    total_users = db_query("SELECT COUNT(*) FROM users")[0][0]
    total_views = db_query("SELECT COUNT(*) FROM views_log")[0][0]
    views_today = db_query("SELECT COUNT(*) FROM views_log WHERE viewed_at::date = CURRENT_DATE")[0][0]
    
    return {
        'total_videos': total_videos,
        'total_users': total_users,
        'total_views': total_views,
        'views_today': views_today
    }

# ===== [2] أكثر الحلقات مشاهدة اليوم =====
def get_top_episodes_today(limit=5):
    """أكثر الحلقات مشاهدة خلال اليوم"""
    query = """
        SELECT 
            v.v_id, 
            v.series_name, 
            v.ep_num, 
            COUNT(l.id) as view_count
        FROM videos v
        LEFT JOIN views_log l ON v.v_id = l.v_id AND l.viewed_at::date = CURRENT_DATE
        GROUP BY v.v_id, v.series_name, v.ep_num
        HAVING COUNT(l.id) > 0
        ORDER BY view_count DESC
        LIMIT %s;
    """
    return db_query(query, (limit,))

# ===== [3] أقل الحلقات مشاهدة اليوم =====
def get_bottom_episodes_today(limit=5):
    """أقل الحلقات مشاهدة خلال اليوم (أو التي لم تشاهد)"""
    query = """
        SELECT 
            v.v_id, 
            v.series_name, 
            v.ep_num, 
            COUNT(l.id) as view_count
        FROM videos v
        LEFT JOIN views_log l ON v.v_id = l.v_id AND l.viewed_at::date = CURRENT_DATE
        GROUP BY v.v_id, v.series_name, v.ep_num
        ORDER BY view_count ASC, v.v_id ASC
        LIMIT %s;
    """
    return db_query(query, (limit,))

# ===== [4] أكثر الحلقات مشاهدة كل الوقت =====
def get_top_episodes_all_time(limit=5):
    """أكثر الحلقات مشاهدة على الإطلاق"""
    query = """
        SELECT 
            v.series_name, 
            v.ep_num, 
            v.views as view_count
        FROM videos v
        WHERE v.views > 0
        ORDER BY v.views DESC
        LIMIT %s;
    """
    return db_query(query, (limit,))

# ===== [5] أكثر المسلسلات مشاهدة اليوم =====
def get_top_series_today(limit=5):
    """أكثر المسلسلات مشاهدة خلال اليوم"""
    query = """
        SELECT 
            v.series_name,
            COUNT(l.id) as view_count,
            COUNT(DISTINCT v.v_id) as episodes_watched
        FROM videos v
        JOIN views_log l ON v.v_id = l.v_id AND l.viewed_at::date = CURRENT_DATE
        GROUP BY v.series_name
        ORDER BY view_count DESC
        LIMIT %s;
    """
    return db_query(query, (limit,))

# ===== [6] أكثر المسلسلات مشاهدة كل الوقت =====
def get_top_series_all_time(limit=5):
    """أكثر المسلسلات مشاهدة على الإطلاق"""
    query = """
        SELECT 
            series_name,
            SUM(views) as total_views,
            COUNT(*) as episode_count
        FROM videos
        GROUP BY series_name
        HAVING SUM(views) > 0
        ORDER BY total_views DESC
        LIMIT %s;
    """
    return db_query(query, (limit,))

# ===== [7] أقل المسلسلات مشاهدة (مقترحة للحذف) =====
def get_worst_series(limit=5):
    """المسلسلات الأقل مشاهدة (مقترحة للإيقاف)"""
    query = """
        SELECT 
            series_name,
            SUM(views) as total_views,
            COUNT(*) as episode_count
        FROM videos
        GROUP BY series_name
        ORDER BY total_views ASC
        LIMIT %s;
    """
    return db_query(query, (limit,))

# ===== [8] إحصائيات تفصيلية لحلقة محددة =====
def get_episode_stats(v_id):
    """إحصائيات تفصيلية لحلقة محددة"""
    query = """
        SELECT 
            v.v_id,
            v.series_name,
            v.ep_num,
            v.views as total_views,
            COUNT(l.id) as views_today,
            MIN(l.viewed_at) as first_view,
            MAX(l.viewed_at) as last_view
        FROM videos v
        LEFT JOIN views_log l ON v.v_id = l.v_id
        WHERE v.v_id = %s
        GROUP BY v.v_id, v.series_name, v.ep_num, v.views;
    """
    result = db_query(query, (v_id,))
    if result and result[0]:
        return {
            'v_id': result[0][0],
            'series_name': result[0][1],
            'ep_num': result[0][2],
            'total_views': result[0][3] or 0,
            'views_today': result[0][4] or 0,
            'first_view': result[0][5],
            'last_view': result[0][6]
        }
    return None

# ===== [9] إحصائيات المستخدمين النشطين =====
def get_active_users(days=7, limit=5):
    """المستخدمين الأكثر نشاطاً خلال الأيام الماضية"""
    query = """
        SELECT 
            u.user_id,
            u.username,
            u.first_name,
            COUNT(l.id) as view_count,
            MAX(l.viewed_at) as last_active
        FROM users u
        JOIN views_log l ON u.user_id = l.user_id
        WHERE l.viewed_at >= CURRENT_DATE - INTERVAL '%s days'
        GROUP BY u.user_id, u.username, u.first_name
        ORDER BY view_count DESC
        LIMIT %s;
    """
    return db_query(query, (days, limit))

# ===== [10] أمر الإحصائيات الرئيسي =====
def register_stats_commands(app):
    
    @app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
    async def stats_command(client, message):
        """عرض إحصائيات البوت المتقدمة"""
        
        # إحصائيات عامة
        general = get_general_stats()
        
        # أكثر الحلقات مشاهدة اليوم
        top_today = get_top_episodes_today(5)
        
        # أقل الحلقات مشاهدة اليوم
        bottom_today = get_bottom_episodes_today(5)
        
        # أكثر المسلسلات مشاهدة كل الوقت
        top_series = get_top_series_all_time(5)
        
        # أقل المسلسلات مشاهدة (مقترحة للحذف)
        worst_series = get_worst_series(5)
        
        # بناء الرسالة
        text = f"📊 **إحصائيات البوت المتقدمة**\n"
        text += f"━━━━━━━━━━━━━━━\n"
        text += f"📁 الحلقات: {general['total_videos']}\n"
        text += f"👥 المستخدمين: {general['total_users']}\n"
        text += f"👀 إجمالي المشاهدات: {general['total_views']}\n"
        text += f"📅 مشاهدات اليوم: {general['views_today']}\n\n"
        
        text += f"🔥 **أكثر 5 حلقات مشاهدة اليوم:**\n"
        if top_today:
            for v_id, name, ep, count in top_today:
                text += f"• {name} - حلقة {ep}: 👁️ {count}\n"
        else:
            text += "• لا توجد مشاهدات اليوم\n"
        
        text += f"\n📉 **أقل 5 حلقات مشاهدة اليوم:**\n"
        if bottom_today:
            for v_id, name, ep, count in bottom_today:
                if count == 0:
                    text += f"• {name} - حلقة {ep}: لم يشاهدها أحد ❌\n"
                else:
                    text += f"• {name} - حلقة {ep}: 👁️ {count} فقط\n"
        else:
            text += "• لا توجد بيانات كافية\n"
        
        text += f"\n🏆 **أكثر 5 مسلسلات مشاهدة:**\n"
        if top_series:
            for name, views, eps in top_series:
                text += f"• {name}: {views} مشاهدة ({eps} حلقة)\n"
        else:
            text += "• لا توجد بيانات\n"
        
        text += f"\n⚠️ **المسلسلات الأقل مشاهدة (مقترحة للحذف):**\n"
        if worst_series:
            for name, views, eps in worst_series:
                if views == 0:
                    text += f"• {name}: لم يشاهدها أحد ❌\n"
                else:
                    text += f"• {name}: {views} مشاهدة فقط\n"
        else:
            text += "• لا توجد بيانات\n"
        
        await message.reply_text(text)
    
    @app.on_message(filters.command("ep_stats") & filters.user(ADMIN_ID))
    async def episode_stats_command(client, message):
        """إحصائيات تفصيلية لحلقة محددة"""
        try:
            command_parts = message.text.split()
            if len(command_parts) < 2:
                await message.reply_text("❌ استخدم: /ep_stats v_id\nمثال: `/ep_stats 3514`")
                return
            
            v_id = command_parts[1]
            stats = get_episode_stats(v_id)
            
            if not stats:
                await message.reply_text(f"❌ لا توجد إحصائيات للحلقة {v_id}")
                return
            
            text = f"📊 **إحصائيات الحلقة {v_id}**\n"
            text += f"━━━━━━━━━━━━━━━\n"
            text += f"🎬 المسلسل: {stats['series_name']}\n"
            text += f"🔢 رقم الحلقة: {stats['ep_num']}\n"
            text += f"👀 إجمالي المشاهدات: {stats['total_views']}\n"
            text += f"📅 مشاهدات اليوم: {stats['views_today']}\n"
            
            if stats['first_view']:
                text += f"🕐 أول مشاهدة: {stats['first_view'].strftime('%Y-%m-%d %H:%M')}\n"
            if stats['last_view']:
                text += f"🕐 آخر مشاهدة: {stats['last_view'].strftime('%Y-%m-%d %H:%M')}\n"
            
            await message.reply_text(text)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")
    
    @app.on_message(filters.command("active_users") & filters.user(ADMIN_ID))
    async def active_users_command(client, message):
        """عرض المستخدمين الأكثر نشاطاً"""
        try:
            command_parts = message.text.split()
            days = 7
            if len(command_parts) > 1:
                days = int(command_parts[1])
            
            users = get_active_users(days, 10)
            
            if not users:
                await message.reply_text(f"📭 لا يوجد نشاط للمستخدمين خلال آخر {days} أيام")
                return
            
            text = f"👥 **المستخدمين الأكثر نشاطاً (آخر {days} أيام)**\n"
            text += f"━━━━━━━━━━━━━━━\n\n"
            
            for user_id, username, first_name, views, last_active in users:
                name = first_name or username or str(user_id)
                time_str = last_active.strftime("%Y-%m-%d %H:%M") if last_active else "غير معروف"
                text += f"• {name}: {views} مشاهدة\n"
                text += f"  آخر نشاط: {time_str}\n\n"
            
            await message.reply_text(text)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")