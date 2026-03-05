#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تليجرام لنشر المسلسلات - نسخة مستقرة لـ Railway
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
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

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

# اتصال قاعدة بيانات مع تحسين الأداء
engine = create_engine(
    DATABASE_URL if DATABASE_URL else 'sqlite:///series_bot.db',
    echo=False,
    poolclass=NullPool,  # عدم استخدام pool لمنع مشاكل timeout
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
    """إدارة جلسة قاعدة البيانات بشكل آمن"""
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
        self.is_running = True
        logger.info("✅ تم تهيئة البوت")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /start"""
        user = update.effective_user
        
        # حفظ المستخدم
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
            "🔍 /scan - مسح القناة المصدر\n"
            "📤 /post - نشر الحلقات\n"
            "📊 /stats - الإحصائيات\n"
            "❓ /help - المساعدة",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /help"""
        await update.message.reply_text(
            "📚 *مساعدة البوت*\n\n"
            "1️⃣ أضف البوت كمشرف في جميع القنوات\n"
            "2️⃣ استخدم /scan لمرة واحدة فقط\n"
            "3️⃣ استخدم /post للنشر\n\n"
            "• الاشتراك مطلوب للمشاهدة",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /stats"""
        try:
            with get_db() as db:
                total = db.query(Episode).count()
                posted = db.query(Episode).filter(Episode.is_posted == True).count()
                users = db.query(User).count()
            
            await update.message.reply_text(
                f"📊 *الإحصائيات*\n\n"
                f"📹 إجمالي: {total}\n"
                f"✅ منشور: {posted}\n"
                f"⏳ متبقي: {total - posted}\n"
                f"👥 مستخدمين: {users}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            await update.message.reply_text("❌ حدث خطأ")
    
    async def scan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /scan - نسخة محسنة"""
        status_msg = await update.message.reply_text(
            "🔄 *جاري مسح القناة المصدر...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            with get_db() as db:
                scanned = 0
                added = 0
                
                # جلب آخر 50 رسالة فقط (لتجنب timeout)
                try:
                    messages = []
                    async for message in context.bot.get_chat_history(
                        chat_id=SOURCE_CHANNEL,
                        limit=50
                    ):
                        messages.append(message)
                        scanned += 1
                        
                        if message.video:
                            # التحقق من عدم التكرار
                            existing = db.query(Episode).filter(
                                Episode.message_id == message.message_id
                            ).first()
                            
                            if not existing:
                                caption = message.caption or ""
                                series_name, ep_num, ep_name = self.extract_info(caption)
                                
                                poster_id = message.photo[-1].file_id if message.photo else None
                                
                                new_ep = Episode(
                                    message_id=message.message_id,
                                    series_name=series_name,
                                    episode_number=ep_num,
                                    episode_name=ep_name,
                                    video_file_id=message.video.file_id,
                                    poster_file_id=poster_id,
                                    quality=self.get_quality(message.video),
                                    duration=message.video.duration or 0,
                                    caption=caption
                                )
                                db.add(new_ep)
                                added += 1
                                
                                if added % 10 == 0:
                                    await status_msg.edit_text(
                                        f"🔄 تم العثور على {added} حلقة...",
                                        parse_mode=ParseMode.MARKDOWN
                                    )
                    
                    db.commit()
                    
                except Exception as e:
                    logger.error(f"خطأ في جلب الرسائل: {e}")
                    await status_msg.edit_text(f"❌ خطأ: {str(e)}")
                    return
                
            await status_msg.edit_text(
                f"✅ *تم المسح*\n\n"
                f"📊 فحص: {scanned} رسالة\n"
                f"✅ جديد: {added} حلقة",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"خطأ في المسح: {e}")
            await status_msg.edit_text(f"❌ خطأ: {str(e)}")
    
    def extract_info(self, caption: str) -> Tuple[str, int, str]:
        """استخراج معلومات الحلقة"""
        if not caption:
            return "مسلسل", 0, "حلقة"
        
        # أنماط بسيطة
        patterns = [
            r'(.+?)[\s\-_]+(\d+)[\s\-_]+(.+)',
            r'(.+?)[\s\-_]+الحلقة[\s\-_]*(\d+)',
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
                ep_name = groups[2].strip() if len(groups) > 2 else f"حلقة {ep_num}"
                return series, ep_num, ep_name
        
        return caption, 0, caption
    
    def get_quality(self, video) -> str:
        """تحديد الجودة"""
        if hasattr(video, 'height') and video.height:
            if video.height >= 2160:
                return "4K"
            elif video.height >= 1080:
                return "Full HD"
            elif video.height >= 720:
                return "HD"
        return "HD"
    
    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نشر الحلقات - نسخة محسنة"""
        status_msg = await update.message.reply_text(
            "🔄 *جاري نشر الحلقات...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            with get_db() as db:
                # جلب حلقتين فقط كل مرة
                episodes = db.query(Episode).filter(
                    Episode.is_posted == False
                ).order_by(Episode.id).limit(2).all()
                
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
                            f"📺 حلقة {ep.episode_number}\n"
                            f"📝 {ep.episode_name}\n"
                            f"⏱ {minutes}:{seconds:02d}\n"
                            f"⚡ {ep.quality}\n\n"
                            f"👇 اضغط للمشاهدة"
                        )
                        
                        keyboard = [[
                            InlineKeyboardButton("▶️ مشاهدة", callback_data=f"watch_{ep.id}")
                        ]]
                        
                        if ep.poster_file_id:
                            await context.bot.send_photo(
                                chat_id=TARGET_CHANNEL,
                                photo=ep.poster_file_id,
                                caption=text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=TARGET_CHANNEL,
                                text=text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode=ParseMode.MARKDOWN
                            )
                        
                        ep.is_posted = True
                        posted += 1
                        await asyncio.sleep(3)  # زيادة التاخير
                        
                    except Exception as e:
                        logger.error(f"خطأ: {e}")
                
                db.commit()
                
            await status_msg.edit_text(f"✅ تم نشر {posted} حلقة")
            
        except Exception as e:
            logger.error(f"خطأ في النشر: {e}")
            await status_msg.edit_text(f"❌ خطأ")
    
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
        
        # التحقق من الاشتراك
        if not await self.check_sub(query.from_user.id, context):
            keyboard = [[
                InlineKeyboardButton("🔔 اشترك", url="https://t.me/+7AC_HNR8QFI5OWY0")
            ]]
            await query.edit_message_text(
                "⚠️ اشترك أولاً",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # إرسال الفيديو
        if query.data.startswith("watch_"):
            ep_id = int(query.data.split("_")[1])
            
            with get_db() as db:
                ep = db.query(Episode).filter(Episode.id == ep_id).first()
                
                if ep and ep.video_file_id:
                    await context.bot.send_video(
                        chat_id=query.from_user.id,
                        video=ep.video_file_id,
                        caption=f"🎬 {ep.series_name} - حلقة {ep.episode_number}",
                        supports_streaming=True
                    )
                    await query.edit_message_text("✅ تم الإرسال")
                else:
                    await query.edit_message_text("❌ غير متوفرة")
    
    def stop(self):
        """إيقاف البوت"""
        self.is_running = False
        logger.info("🛑 جاري إيقاف البوت...")
    
    def run(self):
        """تشغيل البوت"""
        try:
            # إعداد معالج إشارة الإيقاف
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            def signal_handler():
                logger.info("📥 استقبال إشارة إيقاف...")
                self.stop()
                loop.stop()
            
            for sig in [signal.SIGINT, signal.SIGTERM]:
                loop.add_signal_handler(sig, signal_handler)
            
            # إنشاء التطبيق
            self.application = Application.builder().token(BOT_TOKEN).build()
            
            # إضافة المعالجات
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("scan", self.scan_command))
            self.application.add_handler(CommandHandler("post", self.post_command))
            self.application.add_handler(CallbackQueryHandler(self.button_handler))
            
            logger.info("✅ البوت يعمل!")
            
            # تشغيل البوت
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                timeout=30
            )
            
        except Exception as e:
            logger.error(f"❌ خطأ في التشغيل: {e}")
        finally:
            logger.info("👋 تم إيقاف البوت")

# ======================= التشغيل =======================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 تشغيل البوت...")
    print("=" * 50)
    
    bot = SeriesBot()
    
    try:
        bot.run()
    except KeyboardInterrupt:
        bot.stop()
        sys.exit(0)
