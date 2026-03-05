#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تليجرام لنشر المسلسلات - نسخة نهائية مع إصلاح مشكلة قاعدة البيانات
تم التطوير للنشر على Railway.app
"""

import os
import sys
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from contextlib import contextmanager
import signal

# المكتبات المطلوبة
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.error import TimedOut, NetworkError, RetryAfter

# SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Text, Boolean, DateTime, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError, ProgrammingError

# ======================= الإعدادات =======================

# توكن البوت
BOT_TOKEN = os.getenv('BOT_TOKEN', '8579897728:AAF_jh9HnSNdHfkVhrjVeeagsQmYh6Jfo')

# معرفات القنوات
SOURCE_CHANNEL = -1003547072209      # القناة المصدر
TARGET_CHANNEL = -1003554018307      # قناة النشر
FORCE_CHANNEL = -1003894735143       # قناة الاشتراك الإجباري

# رابط قاعدة البيانات
DATABASE_URL = os.getenv('DATABASE_URL', '')

# إعداد التسجيل المحسن
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ======================= قاعدة البيانات مع الإصلاح =======================

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# إنشاء اتصال قاعدة البيانات
try:
    engine = create_engine(
        DATABASE_URL if DATABASE_URL else 'sqlite:///series_bot.db',
        echo=False,
        poolclass=NullPool,
        connect_args={'connect_timeout': 10} if DATABASE_URL else {}
    )
    logger.info("✅ تم إنشاء اتصال قاعدة البيانات")
except Exception as e:
    logger.error(f"❌ خطأ في إنشاء اتصال قاعدة البيانات: {e}")
    # استخدام SQLite كبديل احتياطي
    engine = create_engine('sqlite:///series_bot.db', echo=False)
    logger.info("✅ تم استخدام SQLite كبديل احتياطي")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Episode(Base):
    """جدول الحلقات"""
    __tablename__ = 'episodes'
    
    # تعريف الأعمدة بشكل صريح
    id = Column(Integer, primary_key=True)
    message_id = Column(BigInteger, unique=True)
    series_name = Column(String(500))
    episode_number = Column(Integer, default=0)
    episode_name = Column(String(500))
    video_file_id = Column(String(500))
    poster_file_id = Column(String(500), nullable=True)
    quality = Column(String(50), default="HD")
    duration = Column(Integer, default=0)
    caption = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_posted = Column(Boolean, default=False)
    posted_at = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)

class User(Base):
    """جدول المستخدمين"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255))
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_interaction = Column(DateTime, default=datetime.utcnow)

def init_database():
    """تهيئة قاعدة البيانات مع التحقق من الأعمدة وإصلاح المشاكل"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info("🔄 جاري تهيئة قاعدة البيانات...")
            
            # محاولة إنشاء الجداول
            Base.metadata.create_all(bind=engine)
            logger.info("✅ تم إنشاء/تحديث جداول قاعدة البيانات")
            
            # التحقق من وجود الأعمدة المطلوبة
            inspector = inspect(engine)
            
            # التحقق من جدول episodes
            if 'episodes' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('episodes')]
                logger.info(f"📊 الأعمدة الموجودة في جدول episodes: {columns}")
                
                # التحقق من وجود العمود id
                if 'id' not in columns:
                    logger.warning("⚠️ العمود id غير موجود، جاري إعادة بناء الجدول...")
                    
                    # نسخ البيانات الموجودة إذا أمكن
                    try:
                        # محاولة حفظ البيانات القديمة
                        old_data = []
                        with SessionLocal() as session:
                            try:
                                # محاولة جلب البيانات بالطريقة القديمة
                                result = session.execute("SELECT * FROM episodes")
                                old_data = result.fetchall()
                                logger.info(f"📦 تم حفظ {len(old_data)} حلقة قديمة")
                            except:
                                logger.info("ℹ️ لا توجد بيانات قديمة أو لا يمكن الوصول إليها")
                    except:
                        old_data = []
                    
                    # حذف الجدول القديم
                    Episode.__table__.drop(engine)
                    logger.info("✅ تم حذف الجدول القديم")
                    
                    # إنشاء الجدول الجديد
                    Base.metadata.create_all(bind=engine)
                    logger.info("✅ تم إنشاء الجدول الجديد")
                    
                    # محاولة استعادة البيانات القديمة إذا كانت متوفرة
                    if old_data:
                        try:
                            with SessionLocal() as session:
                                for row in old_data:
                                    # تحويل البيانات القديمة إلى الصيغة الجديدة
                                    new_ep = Episode(
                                        message_id=row[1] if len(row) > 1 else 0,
                                        series_name=row[2] if len(row) > 2 else "مسلسل",
                                        episode_number=row[3] if len(row) > 3 else 0,
                                        episode_name=row[4] if len(row) > 4 else "حلقة",
                                        video_file_id=row[5] if len(row) > 5 else "",
                                        poster_file_id=row[6] if len(row) > 6 else None,
                                        quality=row[7] if len(row) > 7 else "HD",
                                        duration=row[8] if len(row) > 8 else 0,
                                        caption=row[9] if len(row) > 9 else "",
                                        is_posted=row[11] if len(row) > 11 else False
                                    )
                                    session.add(new_ep)
                                session.commit()
                                logger.info(f"✅ تم استعادة {len(old_data)} حلقة")
                        except Exception as e:
                            logger.error(f"❌ خطأ في استعادة البيانات: {e}")
            else:
                logger.info("📋 جدول episodes غير موجود، سيتم إنشاؤه")
                Base.metadata.create_all(bind=engine)
            
            # التحقق من جدول users
            if 'users' not in inspector.get_table_names():
                logger.info("📋 جدول users غير موجود، سيتم إنشاؤه")
                Base.metadata.create_all(bind=engine)
            
            logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")
            return True
            
        except Exception as e:
            retry_count += 1
            logger.error(f"❌ محاولة {retry_count} فشلت: {e}")
            if retry_count < max_retries:
                logger.info(f"🔄 إعادة المحاولة بعد 3 ثوان...")
                time.sleep(3)
            else:
                logger.error("❌ فشلت جميع محاولات تهيئة قاعدة البيانات")
                return False

# تهيئة قاعدة البيانات
init_database()

@contextmanager
def get_db():
    """الحصول على جلسة قاعدة البيانات مع معالجة الأخطاء"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except OperationalError as e:
        db.rollback()
        logger.error(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
        # محاولة إعادة الاتصال
        try:
            db.close()
        except:
            pass
    except Exception as e:
        db.rollback()
        logger.error(f"❌ خطأ في قاعدة البيانات: {e}")
    finally:
        try:
            db.close()
        except:
            pass

# ======================= البوت الرئيسي =======================

class SeriesBot:
    def __init__(self):
        self.application = None
        self.start_time = datetime.utcnow()
        logger.info("✅ تم تهيئة البوت - الإصدار النهائي مع إصلاح قاعدة البيانات")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /start"""
        user = update.effective_user
        
        try:
            with get_db() as db:
                existing = db.query(User).filter(User.user_id == user.id).first()
                if not existing:
                    new_user = User(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name or "مستخدم"
                    )
                    db.add(new_user)
                    logger.info(f"👤 مستخدم جديد: {user.id} - {user.first_name}")
                else:
                    existing.last_interaction = datetime.utcnow()
        except Exception as e:
            logger.error(f"خطأ في حفظ المستخدم: {e}")
        
        welcome_text = (
            f"🎬 *مرحباً بك {user.first_name or 'مستخدم'}!*\n\n"
            "أهلاً في *بوت نشر المسلسلات*\n\n"
            "📌 *الأوامر المتاحة:*\n"
            "📤 /post - نشر الحلقات (3 حلقات كل مرة)\n"
            "📊 /stats - عرض الإحصائيات\n"
            "🆘 /help - المساعدة\n\n"
            "💡 *لإضافة حلقات:*\n"
            "• أعد توجيه أي فيديو إلى البوت\n"
            "• البوت سيحفظه تلقائياً"
        )
        
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /help"""
        help_text = (
            "📚 *مساعدة البوت*\n\n"
            "*1️⃣ إضافة الحلقات:*\n"
            "• اذهب إلى القناة المصدر\n"
            "• أعد توجيه أي فيديو إلى البوت\n"
            "• البوت يستخرج المعلومات تلقائياً\n\n"
            "*2️⃣ نشر الحلقات:*\n"
            "• استخدم /post لنشر 3 حلقات جديدة\n"
            "• كل حلقة تنشر مع زر مشاهدة\n\n"
            "*3️⃣ المشاهدة:*\n"
            "• المستخدم يضغط على زر المشاهدة\n"
            "• يتحقق البوت من الاشتراك الإجباري\n"
            "• يتم إرسال الفيديو مباشرة\n\n"
            "*4️⃣ الإحصائيات:*\n"
            "• استخدم /stats لمشاهدة إحصائيات البوت\n\n"
            "⚡ *حالة البوت:* يعمل بكفاءة"
        )
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /stats"""
        try:
            with get_db() as db:
                total = db.query(Episode).count()
                posted = db.query(Episode).filter(Episode.is_posted == True).count()
                pending = total - posted
                users = db.query(User).count()
                series = db.query(Episode.series_name).distinct().count()
                
                # إحصائيات إضافية
                failed = db.query(Episode).filter(Episode.error_count > 0).count()
                
            uptime = datetime.utcnow() - self.start_time
            hours = uptime.seconds // 3600
            minutes = (uptime.seconds % 3600) // 60
            
            stats_text = (
                "📊 *إحصائيات البوت*\n\n"
                f"📹 *إجمالي الحلقات:* {total}\n"
                f"✅ *منشورة:* {posted}\n"
                f"⏳ *متبقية:* {pending}\n"
                f"🎭 *مسلسلات:* {series}\n"
                f"👥 *المستخدمين:* {users}\n"
                f"⚠️ *فشل في النشر:* {failed}\n\n"
                f"⚡ *مدة التشغيل:* {hours}h {minutes}m\n"
                f"🟢 *الحالة:* نشط"
            )
            
            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"خطأ في الإحصائيات: {e}")
            await update.message.reply_text("❌ حدث خطأ في جلب الإحصائيات")
    
    async def handle_forwarded_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الفيديوهات المعاد توجيهها"""
        message = update.message
        
        if not message.video:
            await message.reply_text("❌ هذا ليس فيديو. الرجاء إعادة توجيه فيديو فقط.")
            return
        
        try:
            with get_db() as db:
                # التحقق من التكرار
                existing = db.query(Episode).filter(
                    Episode.message_id == message.message_id
                ).first()
                
                if existing:
                    await message.reply_text("✅ هذه الحلقة موجودة مسبقاً في قاعدة البيانات")
                    return
                
                # استخراج المعلومات
                caption = message.caption or ""
                series_name, ep_num, ep_name = self.extract_info(caption)
                
                # البحث عن الصورة المصغرة
                poster_id = None
                if message.photo:
                    poster_id = message.photo[-1].file_id
                
                # حفظ الحلقة
                new_ep = Episode(
                    message_id=message.message_id,
                    series_name=series_name,
                    episode_number=ep_num,
                    episode_name=ep_name,
                    video_file_id=message.video.file_id,
                    poster_file_id=poster_id,
                    quality=self.get_quality(message.video),
                    duration=message.video.duration or 0,
                    caption=caption,
                    is_posted=False
                )
                db.add(new_ep)
                db.commit()
                
                # تحضير رسالة التأكيد
                minutes = message.video.duration // 60 if message.video.duration else 0
                seconds = message.video.duration % 60 if message.video.duration else 0
                
                await message.reply_text(
                    f"✅ *تم حفظ الحلقة بنجاح!*\n\n"
                    f"🎬 *المسلسل:* {series_name}\n"
                    f"📺 *رقم الحلقة:* {ep_num}\n"
                    f"📝 *الاسم:* {ep_name}\n"
                    f"⏱ *المدة:* {minutes}:{seconds:02d}\n"
                    f"⚡ *الجودة:* {self.get_quality(message.video)}\n\n"
                    f"استخدم /post لنشر الحلقة",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                logger.info(f"✅ تم حفظ حلقة: {series_name} - حلقة {ep_num}")
                
        except Exception as e:
            logger.error(f"خطأ في حفظ الفيديو: {e}")
            await message.reply_text("❌ حدث خطأ في حفظ الفيديو")
    
    def extract_info(self, caption: str) -> Tuple[str, int, str]:
        """استخراج معلومات الحلقة - نسخة محسنة"""
        if not caption:
            return "مسلسل", 0, "حلقة"
        
        caption = caption.strip()
        
        # أنماط بحث متعددة
        patterns = [
            # نمط: اسم المسلسل - الحلقة 10 - اسم الحلقة
            r'(.+?)[\s\-_]+(?:الحلقة|episode|ح)[\s\-_#]*(\d+)[\s\-_]+(.+)',
            # نمط: اسم المسلسل - 10 - اسم الحلقة
            r'(.+?)[\s\-_]+(\d+)[\s\-_]+(.+)',
            # نمط: اسم المسلسل - الحلقة 10
            r'(.+?)[\s\-_]+(?:الحلقة|episode|ح)[\s\-_#]*(\d+)',
            # نمط: اسم المسلسل #10
            r'(.+?)[\s\-_]*#(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, caption, re.IGNORECASE)
            if match:
                groups = match.groups()
                series = groups[0].strip()
                
                try:
                    ep_num = int(groups[1])
                except (ValueError, IndexError):
                    ep_num = 0
                
                ep_name = groups[2].strip() if len(groups) > 2 else f"حلقة {ep_num}"
                
                # تنظيف النتائج
                series = re.sub(r'[\-_#]', ' ', series).strip()
                series = re.sub(r'\s+', ' ', series)
                
                return series, ep_num, ep_name
        
        # إذا لم يتم العثور على نمط، نبحث عن أرقام
        numbers = re.findall(r'\d+', caption)
        if numbers:
            return caption, int(numbers[0]), caption
        
        return caption, 0, caption
    
    def get_quality(self, video) -> str:
        """تحديد جودة الفيديو"""
        if hasattr(video, 'height') and video.height:
            if video.height >= 2160:
                return "4K"
            elif video.height >= 1080:
                return "Full HD"
            elif video.height >= 720:
                return "HD"
            elif video.height >= 480:
                return "SD"
        return "HD"
    
    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /post - النسخة النهائية المُختبرة"""
        status_msg = await update.message.reply_text(
            "🔄 *جاري تجهيز الحلقات للنشر...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            with get_db() as db:
                # جلب الحلقات غير المنشورة
                episodes = db.query(Episode).filter(
                    Episode.is_posted == False
                ).order_by(Episode.id).limit(3).all()
                
                if not episodes:
                    await status_msg.edit_text("✅ لا توجد حلقات جديدة للنشر")
                    return
                
                # تعريف المتغيرات
                posted_count = 0
                failed_count = 0
                success_list = []
                error_list = []
                
                for episode in episodes:
                    try:
                        # تحضير النص
                        minutes = episode.duration // 60
                        seconds = episode.duration % 60
                        
                        text = (
                            f"🎬 *{episode.series_name}*\n"
                            f"📺 *الحلقة {episode.episode_number}*\n"
                            f"📝 {episode.episode_name}\n"
                            f"⏱ المدة: {minutes}:{seconds:02d}\n"
                            f"⚡ الجودة: {episode.quality}\n\n"
                            f"👇 اضغط للمشاهدة"
                        )
                        
                        # إنشاء الأزرار
                        keyboard = [
                            [InlineKeyboardButton("▶️ مشاهدة", callback_data=f"watch_{episode.id}")],
                            [InlineKeyboardButton("📢 القناة", url="https://t.me/+PyUeOtPN1fs0NDA0")]
                        ]
                        
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        # إرسال المنشور
                        if episode.poster_file_id:
                            await context.bot.send_photo(
                                chat_id=TARGET_CHANNEL,
                                photo=episode.poster_file_id,
                                caption=text,
                                reply_markup=reply_markup,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=TARGET_CHANNEL,
                                text=text,
                                reply_markup=reply_markup,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        
                        # تحديث حالة الحلقة
                        episode.is_posted = True
                        episode.posted_at = datetime.utcnow()
                        posted_count += 1
                        success_list.append(f"✅ {episode.series_name} - حلقة {episode.episode_number}")
                        
                        # تحديث رسالة الحالة
                        await status_msg.edit_text(
                            f"🔄 تم نشر {posted_count} من {len(episodes)}...",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        
                        # تأخير بين المنشورات
                        await asyncio.sleep(2)
                        
                    except RetryAfter as e:
                        # مشكلة تجاوز الحدود
                        logger.warning(f"تجاوز الحدود، انتظار {e.retry_after} ثانية")
                        episode.error_count += 1
                        failed_count += 1
                        error_list.append(f"⚠️ {episode.series_name} - حلقة {episode.episode_number}: تجاوز الحدود")
                        await asyncio.sleep(e.retry_after)
                        
                    except Exception as e:
                        # أخطاء أخرى
                        logger.error(f"خطأ في نشر الحلقة {episode.id}: {e}")
                        episode.error_count += 1
                        failed_count += 1
                        error_list.append(f"❌ {episode.series_name} - حلقة {episode.episode_number}: {str(e)[:30]}")
                
                db.commit()
                
                # إعداد تقرير النتيجة
                result_text = (
                    f"✅ *نتيجة النشر*\n\n"
                    f"📊 *الإحصائيات:*\n"
                    f"✅ تم النشر: {posted_count}\n"
                    f"❌ فشل: {failed_count}\n"
                )
                
                if success_list:
                    result_text += f"\n📋 *النجاح:*\n" + "\n".join(success_list[:3])
                
                if error_list and failed_count > 0:
                    result_text += f"\n\n⚠️ *الأخطاء:*\n" + "\n".join(error_list[:3])
                
                await status_msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
                
        except Exception as e:
            logger.error(f"خطأ في النشر: {e}")
            await status_msg.edit_text(f"❌ خطأ في النشر: {str(e)}")
    
    async def check_subscription(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """التحقق من الاشتراك في القناة الإجبارية"""
        try:
            member = await context.bot.get_chat_member(
                chat_id=FORCE_CHANNEL,
                user_id=user_id
            )
            return member.status in ['member', 'administrator', 'creator']
        except Exception as e:
            logger.error(f"خطأ في التحقق: {e}")
            return False
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأزرار"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # التحقق من الاشتراك
        if not await self.check_subscription(user_id, context):
            keyboard = [[
                InlineKeyboardButton("🔔 اشترك", url="https://t.me/+7AC_HNR8QFI5OWY0")
            ]]
            await query.edit_message_text(
                "⚠️ *يجب الاشتراك أولاً*\n\n"
                "للتمكن من المشاهدة، اشترك في القناة ثم اضغط مجدداً",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # معالجة طلب المشاهدة
        if query.data.startswith("watch_"):
            episode_id = int(query.data.split("_")[1])
            
            with get_db() as db:
                episode = db.query(Episode).filter(Episode.id == episode_id).first()
                
                if episode and episode.video_file_id:
                    # تحديث آخر تفاعل للمستخدم
                    user = db.query(User).filter(User.user_id == user_id).first()
                    if user:
                        user.last_interaction = datetime.utcnow()
                    
                    # إرسال الفيديو
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=episode.video_file_id,
                        caption=f"🎬 {episode.series_name} - حلقة {episode.episode_number}",
                        supports_streaming=True
                    )
                    
                    await query.edit_message_text(
                        f"✅ *تم الإرسال*\n\n"
                        f"🎬 {episode.series_name}\n"
                        f"📺 حلقة {episode.episode_number}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.edit_message_text("❌ الحلقة غير متوفرة")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأخطاء العام"""
        logger.error(f"حدث خطأ غير متوقع: {context.error}")
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ عذراً، حدث خطأ غير متوقع. تم تسجيل المشكلة وسيتم حلها قريباً."
                )
        except:
            pass
    
    def run(self):
        """تشغيل البوت"""
        try:
            # إنشاء التطبيق
            self.application = Application.builder().token(BOT_TOKEN).build()
            
            # إضافة المعالجات
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("post", self.post_command))
            
            # معالج الفيديوهات
            self.application.add_handler(MessageHandler(
                filters.VIDEO, 
                self.handle_forwarded_video
            ))
            
            # معالج الأزرار
            self.application.add_handler(CallbackQueryHandler(self.button_handler))
            
            # معالج الأخطاء
            self.application.add_error_handler(self.error_handler)
            
            logger.info("=" * 50)
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info(f"📊 قناة النشر: {TARGET_CHANNEL}")
            logger.info(f"🔔 قناة الاشتراك: {FORCE_CHANNEL}")
            logger.info(f"⏱ وقت التشغيل: {self.start_time}")
            logger.info("=" * 50)
            
            # تشغيل البوت
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                timeout=30
            )
            
        except Exception as e:
            logger.error(f"❌ فشل تشغيل البوت: {e}")
            raise e

# ======================= نقطة البداية =======================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 بوت نشر المسلسلات - الإصدار النهائي مع إصلاح قاعدة البيانات")
    print("=" * 60)
    print("\n📋 الإصلاحات المطبقة:")
    print("✅ إصلاح مشكلة العمود id في قاعدة البيانات")
    print("✅ إضافة دالة تهيئة متقدمة للقاعدة")
    print("✅ معالجة أخطاء الاتصال بقاعدة البيانات")
    print("✅ نسخ احتياطي للبيانات عند الحاجة")
    print("=" * 60)
    print("\n⚡ بدء تشغيل البوت...\n")
    
    bot = SeriesBot()
    bot.run()
