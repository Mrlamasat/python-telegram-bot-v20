#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تليجرام لنشر المسلسلات - نسخة نهائية مع جميع الإصلاحات
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

# المكتبات المطلوبة - تم إضافة جميع الاستيرادات
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

BOT_TOKEN = os.getenv('BOT_TOKEN', '8579897728:AAF_jh9HnSNdHfkVhrjVeeagsQmYh6Jfo')

SOURCE_CHANNEL = -1003547072209
TARGET_CHANNEL = -1003554018307
FORCE_CHANNEL = -1003894735143

DATABASE_URL = os.getenv('DATABASE_URL', '')

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ======================= قاعدة البيانات =======================

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# اتصال قاعدة بيانات
engine = create_engine(
    DATABASE_URL if DATABASE_URL else 'sqlite:///series_bot.db',
    echo=False,
    poolclass=NullPool,
    connect_args={'connect_timeout': 10} if DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Episode(Base):
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
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255))
    joined_at = Column(DateTime, default=datetime.utcnow)

# إنشاء الجداول
Base.metadata.create_all(bind=engine)

@contextmanager
def get_db():
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
    def __init__(self):
        self.application = None
        logger.info("✅ تم تهيئة البوت")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
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
        
        await update.message.reply_text(
            f"🎬 *مرحباً {user.first_name or 'مستخدم'}!*\n\n"
            "أهلاً في بوت المسلسلات\n\n"
            "*الأوامر:*\n"
            "📤 /post - نشر الحلقات\n"
            "📊 /stats - الإحصائيات\n"
            "❓ /help - المساعدة\n\n"
            "*لإضافة حلقات:*\n"
            "• أعد توجيه الفيديو إلى البوت",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📚 *مساعدة البوت*\n\n"
            "*كيفية الإضافة:*\n"
            "1️⃣ اذهب إلى القناة المصدر\n"
            "2️⃣ أعد توجيه أي فيديو إلى البوت\n"
            "3️⃣ البوت سيحفظه تلقائياً\n\n"
            "*كيفية النشر:*\n"
            "• استخدم /post لنشر الحلقات\n\n"
            "*ملاحظة:* الاشتراك مطلوب للمشاهدة",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            with get_db() as db:
                total = db.query(Episode).count()
                posted = db.query(Episode).filter(Episode.is_posted == True).count()
                users = db.query(User).count()
            
            await update.message.reply_text(
                f"📊 *الإحصائيات*\n\n"
                f"📹 إجمالي الحلقات: {total}\n"
                f"✅ منشورة: {posted}\n"
                f"⏳ متبقية: {total - posted}\n"
                f"👥 المستخدمين: {users}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            await update.message.reply_text("❌ حدث خطأ")
    
    async def handle_forwarded_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الفيديوهات المعاد توجيهها"""
        message = update.message
        
        if not message.video:
            await message.reply_text("❌ هذا ليس فيديو")
            return
        
        try:
            with get_db() as db:
                # التحقق من عدم التكرار
                existing = db.query(Episode).filter(
                    Episode.message_id == message.message_id
                ).first()
                
                if existing:
                    await message.reply_text("✅ هذه الحلقة موجودة مسبقاً")
                    return
                
                # استخراج المعلومات
                caption = message.caption or ""
                series_name, ep_num, ep_name = self.extract_info(caption)
                
                # البحث عن صورة مصغرة
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
                
                await message.reply_text(
                    f"✅ *تم حفظ الحلقة*\n\n"
                    f"🎬 {series_name}\n"
                    f"📺 حلقة {ep_num}\n"
                    f"⚡ {self.get_quality(message.video)}",
                    parse_mode=ParseMode.MARKDOWN
                )
                
        except Exception as e:
            logger.error(f"خطأ في حفظ الفيديو: {e}")
            await message.reply_text("❌ حدث خطأ في حفظ الفيديو")
    
    def extract_info(self, caption: str) -> Tuple[str, int, str]:
        """استخراج معلومات الحلقة من النص"""
        if not caption:
            return "مسلسل", 0, "حلقة"
        
        # تنظيف النص
        caption = caption.strip()
        
        # أنماط البحث
        patterns = [
            # النمط: اسم المسلسل - الحلقة 10 - اسم الحلقة
            r'(.+?)[\s\-_]+(?:الحلقة|episode|ح)[\s\-_#]*(\d+)[\s\-_]+(.+)',
            # النمط: اسم المسلسل - 10 - اسم الحلقة
            r'(.+?)[\s\-_]+(\d+)[\s\-_]+(.+)',
            # النمط: اسم المسلسل - الحلقة 10
            r'(.+?)[\s\-_]+(?:الحلقة|episode|ح)[\s\-_#]*(\d+)',
            # النمط: اسم المسلسل #10
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
                
                ep_name = groups[2].strip() if len(groups) > 2 else f"الحلقة {ep_num}"
                
                # تنظيف النتائج
                series = re.sub(r'[\-_#]', ' ', series).strip()
                series = re.sub(r'\s+', ' ', series)
                
                return series, ep_num, ep_name
        
        # إذا لم يتم العثور على نمط
        # محاولة استخراج رقم من النص
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
        """نشر الحلقات في القناة المستهدفة"""
        status_msg = await update.message.reply_text(
            "🔄 *جاري نشر الحلقات...*",
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
                        
                        # إنشاء زر المشاهدة
                        keyboard = [[
                            InlineKeyboardButton("▶️ مشاهدة الحلقة", callback_data=f"watch_{episode.id}")
                        ]]
                        
                        # إضافة رابط القناة
                        keyboard.append([
                            InlineKeyboardButton("📢 قناة المسلسلات", url=f"https://t.me/+PyUeOtPN1fs0NDA0")
                        ])
                        
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
                        
                        # تأخير بين المنشورات
                        await asyncio.sleep(2)
                        
                    except Exception as e:
                        logger.error(f"خطأ في نشر الحلقة {episode.id}: {e}")
                        failed += 1
                
                db.commit()
                
            await status_msg.edit_text(
                f"✅ *تم النشر*\n\n"
                f"✅ تم النشر: {posted}\n"
                f"❌ فشل: {failed}",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"خطأ في النشر: {e}")
            await status_msg.edit_text(f"❌ خطأ: {str(e)[:50]}")
    
    async def check_subscription(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """التحقق من اشتراك المستخدم"""
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
        """معالج الضغط على الأزرار"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # التحقق من الاشتراك
        if not await self.check_subscription(user_id, context):
            keyboard = [[
                InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/+7AC_HNR8QFI5OWY0")
            ]]
            await query.edit_message_text(
                "⚠️ *عذراً، يجب الاشتراك في القناة أولاً*\n\n"
                "للتمكن من مشاهدة الحلقات، يرجى الاشتراك ثم الضغط على الزر مجدداً.",
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
                        f"📺 الحلقة {episode.episode_number}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.edit_message_text("❌ عذراً، الحلقة غير متوفرة")
    
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
            
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info(f"📊 قناة النشر: {TARGET_CHANNEL}")
            logger.info(f"🔔 قناة الاشتراك: {FORCE_CHANNEL}")
            
            # تشغيل البوت
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                timeout=30
            )
            
        except Exception as e:
            logger.error(f"❌ خطأ في التشغيل: {e}")
            raise e

# ======================= التشغيل =======================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 بوت نشر المسلسلات - جاهز للتشغيل")
    print("=" * 50)
    print("📌 طريقة الاستخدام:")
    print("1️⃣ أعد توجيه أي فيديو إلى البوت")
    print("2️⃣ استخدم /post لنشر الحلقات")
    print("=" * 50)
    
    bot = SeriesBot()
    bot.run()
