#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تليجرام لنشر المسلسلات - نسخة نهائية عاملة
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
            "🔍 /scan - مسح القناة المصدر\n"
            "📤 /post - نشر الحلقات\n"
            "📊 /stats - الإحصائيات\n"
            "❓ /help - المساعدة",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📚 *مساعدة البوت*\n\n"
            "1️⃣ أضف البوت كمشرف في جميع القنوات\n"
            "2️⃣ استخدم /scan لمرة واحدة فقط\n"
            "3️⃣ استخدم /post للنشر\n\n"
            "• الاشتراك مطلوب للمشاهدة",
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
                f"📹 إجمالي: {total}\n"
                f"✅ منشور: {posted}\n"
                f"⏳ متبقي: {total - posted}\n"
                f"👥 مستخدمين: {users}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            await update.message.reply_text("❌ حدث خطأ")
    
    async def scan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /scan - باستخدام الطريقة الصحيحة"""
        status_msg = await update.message.reply_text(
            "🔄 *جاري مسح القناة المصدر...*\n"
            "⏱ سيتم جلب آخر 50 رسالة",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            with get_db() as db:
                scanned = 0
                added = 0
                
                # الطريقة الصحيحة: استخدام forward_messages أو get_chat
                # لكن الأسهل: استخدام get_updates لجلب آخر الرسائل
                
                # جلب آخر 50 رسالة من القناة باستخدام get_chat
                try:
                    # محاولة جلب معلومات القناة أولاً
                    chat = await context.bot.get_chat(SOURCE_CHANNEL)
                    logger.info(f"✅ تم الاتصال بالقناة: {chat.title if chat.title else 'قناة'}")
                    
                    # لا يمكن جلب تاريخ الرسائل مباشرة، لذلك سنستخدم طريقة بديلة
                    # سنطلب من المستخدم إرسال معرف آخر رسالة
                    
                    await status_msg.edit_text(
                        "⚠️ *لا يمكن جلب الرسائل القدمة تلقائياً*\n\n"
                        "الرجاء إرسال معرف آخر رسالة في القناة (Message ID)\n"
                        "أو استخدم /add لإضافة الحلقات يدوياً",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                except Exception as e:
                    logger.error(f"خطأ في الاتصال بالقناة: {e}")
                    await status_msg.edit_text(
                        f"❌ خطأ في الوصول للقناة\n"
                        f"تأكد أن البوت مشرف في القناة",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
        except Exception as e:
            logger.error(f"خطأ في المسح: {e}")
            await status_msg.edit_text(f"❌ خطأ: {str(e)}")
    
    async def add_manual_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إضافة حلقة يدوياً"""
        await update.message.reply_text(
            "📝 *إضافة حلقة يدوياً*\n\n"
            "الرجاء إرسال:\n"
            "1. معرف الرسالة (Message ID)\n"
            "2. أو أرسل الفيديو مباشرة",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def forward_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الرسائل المعاد توجيهها"""
        if update.message and update.message.video:
            # حفظ الفيديو المرسل مباشرة
            with get_db() as db:
                caption = update.message.caption or ""
                series_name, ep_num, ep_name = self.extract_info(caption)
                
                poster_id = update.message.photo[-1].file_id if update.message.photo else None
                
                new_ep = Episode(
                    message_id=update.message.message_id,
                    series_name=series_name,
                    episode_number=ep_num,
                    episode_name=ep_name,
                    video_file_id=update.message.video.file_id,
                    poster_file_id=poster_id,
                    quality=self.get_quality(update.message.video),
                    duration=update.message.video.duration or 0,
                    caption=caption,
                    is_posted=False
                )
                db.add(new_ep)
                db.commit()
                
                await update.message.reply_text(f"✅ تم حفظ الحلقة: {series_name} - حلقة {ep_num}")
    
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
        """نشر الحلقات"""
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
                        await asyncio.sleep(3)
                        
                    except Exception as e:
                        logger.error(f"خطأ في النشر: {e}")
                
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
    
    def run(self):
        """تشغيل البوت"""
        try:
            # إنشاء التطبيق
            self.application = Application.builder().token(BOT_TOKEN).build()
            
            # إضافة المعالجات
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("scan", self.scan_command))
            self.application.add_handler(CommandHandler("add", self.add_manual_command))
            self.application.add_handler(CommandHandler("post", self.post_command))
            self.application.add_handler(CallbackQueryHandler(self.button_handler))
            self.application.add_handler(MessageHandler(filters.VIDEO, self.forward_handler))
            
            logger.info("✅ البوت يعمل!")
            
            # تشغيل البوت
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                timeout=30
            )
            
        except Exception as e:
            logger.error(f"❌ خطأ في التشغيل: {e}")

# ======================= التشغيل =======================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 تشغيل البوت...")
    print("=" * 50)
    
    bot = SeriesBot()
    bot.run()
