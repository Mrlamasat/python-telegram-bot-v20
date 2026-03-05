#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تليجرام لنشر المسلسلات - نسخة نهائية كاملة
تم التطوير للنشر على Railway.app
"""

import os
import sys
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Tuple, List
from contextlib import contextmanager
import signal

# المكتبات المطلوبة
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.error import TimedOut, NetworkError

# SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Text, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# ======================= الإعدادات =======================

# توكن البوت - ضع التوكن الخاص بك هنا
BOT_TOKEN = os.getenv('BOT_TOKEN', '8579897728:AAF_jh9HnSNdHfkVhrjVeeagsQmYh6Jfo')

# معرفات القنوات (أرقام وليس نصوص)
SOURCE_CHANNEL = -1003547072209      # القناة المصدر (فيها الحلقات)
TARGET_CHANNEL = -1003554018307      # قناة النشر النهائية
FORCE_CHANNEL = -1003894735143       # قناة الاشتراك الإجباري

# رابط قاعدة البيانات - Railway يوفر متغير DATABASE_URL تلقائياً
DATABASE_URL = os.getenv('DATABASE_URL', '')

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ======================= قاعدة البيانات =======================

# تعديل رابط PostgreSQL ليعمل مع SQLAlchemy
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# إنشاء اتصال قاعدة البيانات
engine = create_engine(
    DATABASE_URL if DATABASE_URL else 'sqlite:///series_bot.db',
    echo=False,
    poolclass=NullPool,
    connect_args={'connect_timeout': 10} if DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Episode(Base):
    """جدول الحلقات"""
    __tablename__ = 'episodes'
    
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

class User(Base):
    """جدول المستخدمين"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255))
    joined_at = Column(DateTime, default=datetime.utcnow)

# إنشاء الجداول في قاعدة البيانات
Base.metadata.create_all(bind=engine)

@contextmanager
def get_db():
    """الحصول على جلسة قاعدة البيانات"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"خطأ في قاعدة البيانات: {e}")
    finally:
        db.close()

# ======================= البوت الرئيسي =======================

class SeriesBot:
    """البوت الرئيسي لنشر المسلسلات"""
    
    def __init__(self):
        self.application = None
        logger.info("✅ تم تهيئة البوت")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /start"""
        user = update.effective_user
        
        # حفظ المستخدم في قاعدة البيانات
        try:
            with get_db() as db:
                if not db.query(User).filter(User.user_id == user.id).first():
                    db.add(User(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name or "مستخدم"
                    ))
        except:
            pass
        
        # رسالة الترحيب
        welcome_text = (
            f"🎬 *مرحباً بك {user.first_name or 'مستخدم'}!*\n\n"
            "أهلاً في بوت نشر المسلسلات\n\n"
            "*الأوامر المتاحة:*\n"
            "📤 /post - نشر الحلقات في القناة\n"
            "📊 /stats - عرض الإحصائيات\n"
            "❓ /help - عرض المساعدة\n\n"
            "*لإضافة حلقات جديدة:*\n"
            "• أعد توجيه أي فيديو إلى البوت\n"
            "• البوت سيحفظه تلقائياً"
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /help"""
        help_text = (
            "📚 *مساعدة البوت*\n\n"
            "*كيفية إضافة الحلقات:*\n"
            "1️⃣ اذهب إلى القناة المصدر\n"
            "2️⃣ أعد توجيه أي فيديو إلى البوت\n"
            "3️⃣ البوت سيحفظه تلقائياً في قاعدة البيانات\n\n"
            "*كيفية نشر الحلقات:*\n"
            "• استخدم /post لنشر الحلقات في القناة المستهدفة\n"
            "• البوت ينشر 3 حلقات في كل مرة\n\n"
            "*كيفية المشاهدة:*\n"
            "1️⃣ يضغط المستخدم على زر المشاهدة\n"
            "2️⃣ يتحقق البوت من الاشتراك في القناة الإجبارية\n"
            "3️⃣ يتم إرسال الفيديو مباشرة للمستخدم\n\n"
            "*ملاحظات مهمة:*\n"
            "• البوت يحتاج صلاحيات مشرف في جميع القنوات\n"
            "• قاعدة البيانات تحفظ جميع الحلقات\n"
            "• البوت يعمل 24/7 على Railway"
        )
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /stats"""
        try:
            with get_db() as db:
                total_episodes = db.query(Episode).count()
                posted_episodes = db.query(Episode).filter(Episode.is_posted == True).count()
                pending_episodes = total_episodes - posted_episodes
                total_users = db.query(User).count()
                
                # إحصائيات إضافية
                series_count = db.query(Episode.series_name).distinct().count()
            
            stats_text = (
                "📊 *إحصائيات البوت*\n\n"
                f"📹 *إجمالي الحلقات:* {total_episodes}\n"
                f"✅ *منشورة:* {posted_episodes}\n"
                f"⏳ *متبقية:* {pending_episodes}\n"
                f"🎭 *عدد المسلسلات:* {series_count}\n"
                f"👥 *المستخدمين:* {total_users}\n\n"
                f"⚡ *الحالة:* البوت يعمل بكفاءة"
            )
            
            await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"خطأ في الإحصائيات: {e}")
            await update.message.reply_text("❌ حدث خطأ في جلب الإحصائيات")
    
    async def handle_forwarded_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الفيديوهات المعاد توجيهها - إضافة الحلقات يدوياً"""
        message = update.message
        
        # التحقق من وجود فيديو
        if not message.video:
            await message.reply_text("❌ هذا ليس فيديو. الرجاء إعادة توجيه فيديو فقط.")
            return
        
        try:
            with get_db() as db:
                # التحقق من عدم وجود الحلقة مسبقاً
                existing = db.query(Episode).filter(
                    Episode.message_id == message.message_id
                ).first()
                
                if existing:
                    await message.reply_text("✅ هذه الحلقة موجودة مسبقاً في قاعدة البيانات")
                    return
                
                # استخراج المعلومات من التسمية التوضيحية
                caption = message.caption or ""
                series_name, episode_number, episode_name = self.extract_info(caption)
                
                # البحث عن صورة مصغرة (البوستر)
                poster_id = None
                if message.photo:
                    poster_id = message.photo[-1].file_id
                
                # حفظ الحلقة في قاعدة البيانات
                new_episode = Episode(
                    message_id=message.message_id,
                    series_name=series_name,
                    episode_number=episode_number,
                    episode_name=episode_name,
                    video_file_id=message.video.file_id,
                    poster_file_id=poster_id,
                    quality=self.get_quality(message.video),
                    duration=message.video.duration or 0,
                    caption=caption,
                    is_posted=False
                )
                db.add(new_episode)
                db.commit()
                
                # رسالة تأكيد
                minutes = message.video.duration // 60 if message.video.duration else 0
                seconds = message.video.duration % 60 if message.video.duration else 0
                
                await message.reply_text(
                    f"✅ *تم حفظ الحلقة بنجاح!*\n\n"
                    f"🎬 *المسلسل:* {series_name}\n"
                    f"📺 *رقم الحلقة:* {episode_number}\n"
                    f"📝 *اسم الحلقة:* {episode_name}\n"
                    f"⏱ *المدة:* {minutes}:{seconds:02d}\n"
                    f"⚡ *الجودة:* {self.get_quality(message.video)}\n\n"
                    f"استخدم /post لنشر الحلقة في القناة",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                logger.info(f"✅ تم حفظ حلقة جديدة: {series_name} - حلقة {episode_number}")
                
        except Exception as e:
            logger.error(f"خطأ في حفظ الفيديو: {e}")
            await message.reply_text("❌ حدث خطأ في حفظ الفيديو. الرجاء المحاولة مرة أخرى.")
    
    def extract_info(self, caption: str) -> Tuple[str, int, str]:
        """استخراج معلومات الحلقة من النص"""
        if not caption:
            return "مسلسل", 0, "حلقة"
        
        # تنظيف النص
        caption = caption.strip()
        
        # أنماط مختلفة للبحث
        patterns = [
            # النمط: اسم المسلسل - الحلقة 10 - اسم الحلقة
            r'(.+?)[\s\-_]+(?:الحلقة|episode|ح)[\s\-_#]*(\d+)[\s\-_]+(.+)',
            # النمط: اسم المسلسل - 10 - اسم الحلقة
            r'(.+?)[\s\-_]+(\d+)[\s\-_]+(.+)',
            # النمط: اسم المسلسل - الحلقة 10
            r'(.+?)[\s\-_]+(?:الحلقة|episode|ح)[\s\-_#]*(\d+)',
            # النمط: اسم المسلسل #10
            r'(.+?)[\s\-_]*#(\d+)',
            # النمط: أي نص به رقم
            r'^([^\d]+)(\d+)(.*)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, caption, re.IGNORECASE)
            if match:
                groups = match.groups()
                series = groups[0].strip()
                
                try:
                    episode_number = int(groups[1])
                except (ValueError, IndexError):
                    episode_number = 0
                
                episode_name = groups[2].strip() if len(groups) > 2 else f"الحلقة {episode_number}"
                
                # تنظيف النتائج
                series = re.sub(r'[\-_#]', ' ', series).strip()
                series = re.sub(r'\s+', ' ', series)
                
                return series, episode_number, episode_name
        
        # إذا لم يتم العثور على نمط، نبحث عن أرقام في النص
        numbers = re.findall(r'\d+', caption)
        if numbers:
            return caption, int(numbers[0]), caption
        
        return caption, 0, caption
    
    def get_quality(self, video) -> str:
        """تحديد جودة الفيديو"""
        if hasattr(video, 'height') and video.height:
            if video.height >= 2160:
                return "4K ULTRA HD"
            elif video.height >= 1080:
                return "FULL HD"
            elif video.height >= 720:
                return "HD"
            elif video.height >= 480:
                return "SD"
        return "HD"
    
    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /post - نشر الحلقات في القناة المستهدفة"""
        status_msg = await update.message.reply_text(
            "🔄 *جاري نشر الحلقات...*\n⏱ قد يستغرق هذا بضع لحظات",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            with get_db() as db:
                # جلب 3 حلقات غير منشورة
                episodes = db.query(Episode).filter(
                    Episode.is_posted == False
                ).order_by(Episode.id).limit(3).all()
                
                if not episodes:
                    await status_msg.edit_text("✅ لا توجد حلقات جديدة للنشر")
                    return
                
                posted = 0
                failed = 0
                
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
                            f"👇 اضغط على الزر للمشاهدة"
                        )
                        
                        # إنشاء أزرار التفاعل
                        keyboard = [
                            [InlineKeyboardButton("▶️ مشاهدة الحلقة", callback_data=f"watch_{episode.id}")],
                            [InlineKeyboardButton("📢 قناة المسلسلات", url=f"https://t.me/+PyUeOtPN1fs0NDA0")]
                        ]
                        
                        # إضافة حلقات مشابهة (اختياري)
                        similar = db.query(Episode).filter(
                            Episode.series_name == episode.series_name,
                            Episode.id != episode.id,
                            Episode.is_posted == True
                        ).order_by(Episode.episode_number).limit(5).all()
                        
                        if similar:
                            sim_buttons = []
                            for sim in similar:
                                sim_buttons.append(
                                    InlineKeyboardButton(f"📺 {sim.episode_number}", callback_data=f"watch_{sim.id}")
                                )
                            
                            # تقسيم الأزرار إلى صفوف من 3
                            for i in range(0, len(sim_buttons), 3):
                                keyboard.append(sim_buttons[i:i+3])
                        
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        # إرسال مع أو بدون بوستر
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
                        posted += 1
                        
                        # تحديث رسالة الحالة
                        await status_msg.edit_text(
                            f"🔄 *جاري النشر...*\n\n"
                            f"✅ تم نشر: {posted} حلقة",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        
                        # تأخير بين المنشورات لتجنب تجاوز الحدود
                        await asyncio.sleep(2)
                        
                    except Exception as e:
                        logger.error(f"خطأ في نشر الحلقة {episode.id}: {e}")
                        failed += 1
                
                db.commit()
                
            # رسالة النتيجة النهائية
            result_text = (
                f"✅ *تم النشر بنجاح!*\n\n"
                f"📊 *النتيجة:*\n"
                f"✅ تم نشر: {posted} حلقة\n"
                f"❌ فشل: {failed} حلقة"
            )
            
            if failed > 0:
                result_text += "\n\n⚠️ بعض الحلقات فشلت في النشر. راجع السجلات للمزيد من التفاصيل."
            
            await status_msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"خطأ في النشر: {e}")
            await status_msg.edit_text(f"❌ حدث خطأ في النشر: {str(e)[:100]}")
    
    async def check_subscription(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """التحقق من اشتراك المستخدم في القناة الإجبارية"""
        try:
            member = await context.bot.get_chat_member(
                chat_id=FORCE_CHANNEL,
                user_id=user_id
            )
            return member.status in ['member', 'administrator', 'creator']
        except Exception as e:
            logger.error(f"خطأ في التحقق من الاشتراك: {e}")
            return False
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الضغط على الأزرار"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        # التحقق من الاشتراك الإجباري
        is_subscribed = await self.check_subscription(user_id, context)
        
        if not is_subscribed:
            # عرض زر الاشتراك
            keyboard = [[
                InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/+7AC_HNR8QFI5OWY0")
            ]]
            await query.edit_message_text(
                "⚠️ *عذراً، يجب الاشتراك في القناة أولاً*\n\n"
                "للتمكن من مشاهدة الحلقات، يرجى الاشتراك في القناة ثم الضغط على الزر مجدداً.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # معالجة البيانات
        if data.startswith("watch_"):
            episode_id = int(data.split("_")[1])
            
            with get_db() as db:
                episode = db.query(Episode).filter(Episode.id == episode_id).first()
                
                if episode and episode.video_file_id:
                    # إرسال الفيديو
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=episode.video_file_id,
                        caption=f"🎬 {episode.series_name} - الحلقة {episode.episode_number}\n{episode.episode_name}",
                        supports_streaming=True
                    )
                    
                    # تحديث الرسالة
                    await query.edit_message_text(
                        f"✅ *تم إرسال الحلقة*\n\n"
                        f"🎬 {episode.series_name}\n"
                        f"📺 الحلقة {episode.episode_number}\n"
                        f"⚡ {episode.quality}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.edit_message_text("❌ عذراً، لم نتمكن من العثور على الحلقة")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأخطاء"""
        logger.error(f"حدث خطأ: {context.error}")
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ عذراً، حدث خطأ غير متوقع. الرجاء المحاولة لاحقاً."
                )
        except:
            pass
    
    def run(self):
        """تشغيل البوت"""
        try:
            # إنشاء التطبيق
            self.application = Application.builder().token(BOT_TOKEN).build()
            
            # إضافة معالجات الأوامر
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("post", self.post_command))
            
            # معالج الفيديوهات المعاد توجيهها
            self.application.add_handler(MessageHandler(
                filters.VIDEO, 
                self.handle_forwarded_video
            ))
            
            # معالج الأزرار
            self.application.add_handler(CallbackQueryHandler(self.button_handler))
            
            # معالج الأخطاء
            self.application.add_error_handler(self.error_handler)
            
            # رسالة بدء التشغيل
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info(f"📊 القناة المصدر: {SOURCE_CHANNEL}")
            logger.info(f"📤 قناة النشر: {TARGET_CHANNEL}")
            logger.info(f"🔔 قناة الاشتراك: {FORCE_CHANNEL}")
            
            # بدء البوت
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
    print("🚀 بوت نشر المسلسلات - النسخة النهائية")
    print("=" * 60)
    print("📌 طريقة الاستخدام:")
    print("1️⃣ أعد توجيه أي فيديو إلى البوت")
    print("2️⃣ استخدم /post لنشر الحلقات")
    print("3️⃣ استخدم /stats للإحصائيات")
    print("4️⃣ استخدم /help للمساعدة")
    print("=" * 60)
    
    # إنشاء وتشغيل البوت
    bot = SeriesBot()
    bot.run()
