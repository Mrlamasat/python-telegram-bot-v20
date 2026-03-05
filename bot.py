#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تليجرام لنشر المسلسلات - نسخة Railway
"""

import os
import sys
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Tuple, List
from contextlib import contextmanager

# إعداد المسارات
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# المكتبات المطلوبة
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# SQLAlchemy لقاعدة البيانات
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Text, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# ======================= الإعدادات =======================

# توكن البوت - يفضل وضعه في متغير بيئي
BOT_TOKEN = os.getenv('BOT_TOKEN', '8579897728:AAF_jh9HnSNdHfkVhrjVeeagsQmYh6Jfo')

# معرفات القنوات
SOURCE_CHANNEL = -1003547072209      # القناة المصدر
TARGET_CHANNEL = -1003554018307      # قناة النشر
FORCE_CHANNEL = -1003894735143       # قناة الاشتراك الإجباري

# رابط قاعدة البيانات من Railway
DATABASE_URL = os.getenv('DATABASE_URL', '')

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ======================= قاعدة البيانات =======================

# تعديل رابط PostgreSQL
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# إنشاء اتصال قاعدة البيانات
engine = create_engine(
    DATABASE_URL if DATABASE_URL else 'sqlite:///series_bot.db',
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

class Episode(Base):
    """جدول الحلقات"""
    __tablename__ = 'episodes'
    
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(BigInteger, unique=True, index=True)
    series_name = Column(String(500), index=True)
    episode_number = Column(Integer, default=0)
    episode_name = Column(String(500))
    video_file_id = Column(String(500))
    poster_file_id = Column(String(500), nullable=True)
    quality = Column(String(50), default="HD")
    duration = Column(Integer, default=0)
    caption = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_posted = Column(Boolean, default=False)
    posted_message_id = Column(BigInteger, nullable=True)

class User(Base):
    """جدول المستخدمين"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255))
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, default=datetime.utcnow)

# إنشاء الجداول
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
        raise
    finally:
        db.close()

# ======================= البوت الرئيسي =======================

class SeriesBot:
    def __init__(self):
        self.application = None
        logger.info("✅ تم تهيئة البوت")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /start"""
        user = update.effective_user
        
        try:
            with get_db() as db:
                existing_user = db.query(User).filter(User.user_id == user.id).first()
                if not existing_user:
                    new_user = User(
                        user_id=user.id,
                        username=user.username,
                        first_name=user.first_name or "مستخدم"
                    )
                    db.add(new_user)
                    logger.info(f"👤 مستخدم جديد: {user.id}")
        except Exception as e:
            logger.error(f"خطأ في حفظ المستخدم: {e}")
        
        welcome_text = (
            f"🎬 *مرحباً بك {user.first_name or 'مستخدم'}!*\n\n"
            "أهلاً في بوت نشر المسلسلات\n\n"
            "*الأوامر المتاحة:*\n"
            "🔍 /scan - مسح القناة المصدر\n"
            "📤 /post - نشر الحلقات الجديدة\n"
            "📊 /stats - عرض الإحصائيات\n"
            "❓ /help - المساعدة\n\n"
            "✨ استمتع بالمشاهدة"
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /help"""
        help_text = (
            "📚 *مساعدة البوت*\n\n"
            "*كيفية الاستخدام:*\n"
            "1️⃣ أضف البوت كمشرف في جميع القنوات\n"
            "2️⃣ استخدم /scan لمسح القناة المصدر\n"
            "3️⃣ استخدم /post لنشر الحلقات\n\n"
            "*ملاحظات:*\n"
            "• يجب الاشتراك في القناة الإجبارية للمشاهدة\n"
            "• البوت يعمل تلقائياً على الساعة"
        )
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /stats"""
        try:
            with get_db() as db:
                total = db.query(Episode).count()
                posted = db.query(Episode).filter(Episode.is_posted == True).count()
                users = db.query(User).count()
                series = db.query(Episode.series_name).distinct().count()
            
            stats_text = (
                "📊 *الإحصائيات*\n\n"
                f"📹 الحلقات: {total}\n"
                f"✅ منشورة: {posted}\n"
                f"⏳ متبقية: {total - posted}\n"
                f"🎭 مسلسلات: {series}\n"
                f"👥 المستخدمين: {users}"
            )
            
            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"خطأ في الإحصائيات: {e}")
            await update.message.reply_text("❌ حدث خطأ في جلب الإحصائيات")
    
    async def scan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /scan"""
        status_msg = await update.message.reply_text(
            "🔄 *جاري مسح القناة المصدر...*\n\n⏱ قد يستغرق هذا بضع دقائق",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            with get_db() as db:
                scanned = 0
                added = 0
                offset = 0
                
                while True:
                    try:
                        messages = await context.bot.get_chat_history(
                            chat_id=SOURCE_CHANNEL,
                            limit=100,
                            offset_id=offset
                        )
                    except Exception as e:
                        logger.error(f"خطأ في جلب الرسائل: {e}")
                        await status_msg.edit_text(f"❌ خطأ في الوصول للقناة: {str(e)}")
                        return
                    
                    if not messages:
                        break
                    
                    for message in messages:
                        scanned += 1
                        
                        if message.video:
                            existing = db.query(Episode).filter(
                                Episode.message_id == message.message_id
                            ).first()
                            
                            if not existing:
                                series_name, ep_num, ep_name = self.extract_info(
                                    message.caption or ""
                                )
                                
                                poster_id = None
                                if message.photo:
                                    poster_id = message.photo[-1].file_id
                                
                                new_ep = Episode(
                                    message_id=message.message_id,
                                    series_name=series_name,
                                    episode_number=ep_num,
                                    episode_name=ep_name,
                                    video_file_id=message.video.file_id,
                                    poster_file_id=poster_id,
                                    quality=self.get_quality(message.video),
                                    duration=message.video.duration or 0,
                                    caption=message.caption or ""
                                )
                                db.add(new_ep)
                                added += 1
                        
                        offset = message.message_id
                    
                    await asyncio.sleep(1)
                
                db.commit()
                
            await status_msg.edit_text(
                f"✅ *تم المسح بنجاح!*\n\n"
                f"📊 تم فحص: {scanned} رسالة\n"
                f"✅ تم العثور: {added} حلقة",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"خطأ في المسح: {e}")
            await status_msg.edit_text(f"❌ حدث خطأ: {str(e)}")
    
    def extract_info(self, caption: str) -> Tuple[str, int, str]:
        """استخراج معلومات الحلقة"""
        if not caption:
            return "مسلسل", 0, "حلقة"
        
        # أنماط بسيطة للبحث
        patterns = [
            r'(.+?)[\s\-_]+(\d+)[\s\-_]+(.+)',
            r'(.+?)[\s\-_]+الحلقة[\s\-_]*(\d+)',
            r'(.+?)#(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, caption, re.IGNORECASE)
            if match:
                groups = match.groups()
                series = groups[0].strip()
                try:
                    ep_num = int(groups[1])
                except:
                    ep_num = 0
                ep_name = groups[2].strip() if len(groups) > 2 else f"الحلقة {ep_num}"
                return series, ep_num, ep_name
        
        return caption, 0, caption
    
    def get_quality(self, video) -> str:
        """تحديد الجودة"""
        if hasattr(video, 'height') and video.height:
            if video.height >= 2160:
                return "4K"
            elif video.height >= 1080:
                return "FULL HD"
            elif video.height >= 720:
                return "HD"
        return "HD"
    
    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /post"""
        status_msg = await update.message.reply_text(
            "🔄 *جاري نشر الحلقات...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            with get_db() as db:
                episodes = db.query(Episode).filter(
                    Episode.is_posted == False
                ).order_by(Episode.id).limit(3).all()
                
                if not episodes:
                    await status_msg.edit_text("✅ لا توجد حلقات جديدة")
                    return
                
                posted = 0
                
                for ep in episodes:
                    try:
                        minutes = ep.duration // 60
                        seconds = ep.duration % 60
                        
                        text = (
                            f"🎬 *{ep.series_name}*\n"
                            f"📺 *الحلقة {ep.episode_number}*\n"
                            f"📝 {ep.episode_name}\n"
                            f"⏱ {minutes}:{seconds:02d}\n"
                            f"⚡ {ep.quality}\n\n"
                            f"👇 اضغط للمشاهدة"
                        )
                        
                        keyboard = [[
                            InlineKeyboardButton("▶️ مشاهدة", callback_data=f"watch_{ep.id}")
                        ]]
                        
                        reply = InlineKeyboardMarkup(keyboard)
                        
                        if ep.poster_file_id:
                            await context.bot.send_photo(
                                chat_id=TARGET_CHANNEL,
                                photo=ep.poster_file_id,
                                caption=text,
                                reply_markup=reply,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=TARGET_CHANNEL,
                                text=text,
                                reply_markup=reply,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        
                        ep.is_posted = True
                        posted += 1
                        await asyncio.sleep(2)
                        
                    except Exception as e:
                        logger.error(f"خطأ في نشر الحلقة {ep.id}: {e}")
                
                db.commit()
                
            await status_msg.edit_text(f"✅ تم نشر {posted} حلقة")
            
        except Exception as e:
            logger.error(f"خطأ في النشر: {e}")
            await status_msg.edit_text(f"❌ خطأ: {str(e)}")
    
    async def check_sub(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """التحقق من الاشتراك"""
        try:
            member = await context.bot.get_chat_member(
                chat_id=FORCE_CHANNEL,
                user_id=user_id
            )
            return member.status in ['member', 'administrator', 'creator']
        except:
            return False
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأزرار"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        if not await self.check_sub(user_id, context):
            keyboard = [[
                InlineKeyboardButton("🔔 اشترك", url="https://t.me/+7AC_HNR8QFI5OWY0")
            ]]
            await query.edit_message_text(
                "⚠️ اشترك أولاً",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        data = query.data
        if data.startswith("watch_"):
            ep_id = int(data.split("_")[1])
            
            with get_db() as db:
                ep = db.query(Episode).filter(Episode.id == ep_id).first()
                
                if ep and ep.video_file_id:
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=ep.video_file_id,
                        caption=f"🎬 {ep.series_name} - حلقة {ep.episode_number}",
                        supports_streaming=True
                    )
                    
                    await query.edit_message_text("✅ تم الإرسال")
                else:
                    await query.edit_message_text("❌ غير متوفرة")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأخطاء"""
        logger.error(f"خطأ: {context.error}")
    
    def run(self):
        """تشغيل البوت"""
        try:
            self.application = Application.builder().token(BOT_TOKEN).build()
            
            # إضافة المعالجات
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("scan", self.scan_command))
            self.application.add_handler(CommandHandler("post", self.post_command))
            self.application.add_handler(CallbackQueryHandler(self.button_handler))
            self.application.add_error_handler(self.error_handler)
            
            logger.info("✅ البوت يعمل!")
            logger.info(f"📊 SOURCE: {SOURCE_CHANNEL}")
            logger.info(f"📤 TARGET: {TARGET_CHANNEL}")
            logger.info(f"🔔 FORCE: {FORCE_CHANNEL}")
            
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"❌ فشل التشغيل: {e}")
            raise e

# ======================= التشغيل =======================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 تشغيل البوت...")
    print("=" * 50)
    
    bot = SeriesBot()
    bot.run()
