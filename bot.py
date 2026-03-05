#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
تطوير: محمد المحسن (Mohammed Almohsen)
بوت تليجرام لنشر المسلسلات - النسخة الاحترافية المتوافقة مع Railway و PostgreSQL
"""

import os
import sys
import logging
import asyncio
import re
import time
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from contextlib import contextmanager

# المكتبات المطلوبة
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.error import TimedOut, NetworkError, RetryAfter, BadRequest

# SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Text, Boolean, DateTime, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError

# ======================= الإعدادات =======================

# توكن البوت
BOT_TOKEN = os.getenv('BOT_TOKEN', '8579897728:AAF_jh9HnSNdHfkVhrjVeeagsQmYh6Jfo')

# معرفات القنوات
SOURCE_CHANNEL = -1003547072209      # القناة المصدر
TARGET_CHANNEL = -1003554018307      # قناة النشر
FORCE_CHANNEL = -1003894735143       # قناة الاشتراك الإجباري

# رابط قاعدة البيانات (تم التحديث للرابط الخاص بك)
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ======================= قاعدة البيانات =======================

# إنشاء اتصال قاعدة البيانات مع PostgreSQL
try:
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        connect_args={'connect_timeout': 10}
    )
    logger.info("✅ تم الاتصال بنجاح بقاعدة بيانات PostgreSQL على Railway")
except Exception as e:
    logger.error(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
    sys.exit(1)

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
    posted_at = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255))
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_interaction = Column(DateTime, default=datetime.utcnow)

# تهيئة الجداول
Base.metadata.create_all(bind=engine)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"❌ خطأ قاعدة بيانات: {e}")
    finally:
        db.close()

# ======================= منطق البوت =======================

class SeriesBot:
    def __init__(self):
        self.application = None
        self.start_time = datetime.utcnow()

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        with get_db() as db:
            existing = db.query(User).filter(User.user_id == user.id).first()
            if not existing:
                db.add(User(user_id=user.id, username=user.username, first_name=user.first_name))
        
        await update.message.reply_text(
            f"🎬 *مرحباً بك {user.first_name}!*\n\n"
            "استخدم /post لنشر الحلقات الجديدة، أو قم بتوجيه فيديو ليتم حفظه.",
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_forwarded_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        if not message.video: return

        with get_db() as db:
            if db.query(Episode).filter(Episode.message_id == message.message_id).first():
                await message.reply_text("✅ هذه الحلقة محفوظة مسبقاً.")
                return

            caption = message.caption or ""
            series, num, name = self.extract_info(caption)
            
            new_ep = Episode(
                message_id=message.message_id,
                series_name=series,
                episode_number=num,
                episode_name=name,
                video_file_id=message.video.file_id,
                quality="HD",
                duration=message.video.duration or 0,
                is_posted=False
            )
            db.add(new_ep)
            await message.reply_text(f"✅ تم حفظ: {series} - حلقة {num}")

    def extract_info(self, caption: str):
        # محرك استخراج بسيط ومطور
        pattern = r'(.+?)[\s\-_]+(?:الحلقة|episode|حلقة)[\s\-_#]*(\d+)'
        match = re.search(pattern, caption, re.IGNORECASE)
        if match:
            return match.group(1).strip(), int(match.group(2)), f"الحلقة {match.group(2)}"
        return "مسلسل غير معروف", 0, "حلقة"

    async def post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status_msg = await update.message.reply_text("🔄 جاري النشر...")
        with get_db() as db:
            episodes = db.query(Episode).filter(Episode.is_posted == False).limit(3).all()
            if not episodes:
                await status_msg.edit_text("✅ لا توجد حلقات جديدة.")
                return

            for ep in episodes:
                keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", callback_data=f"watch_{ep.id}")]]
                text = f"🎬 *{ep.series_name}*\n📺 *الحلقة {ep.episode_number}*\n\nاضغط أدناه للمشاهدة 👇"
                
                await context.bot.send_message(
                    chat_id=TARGET_CHANNEL,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                ep.is_posted = True
            await status_msg.edit_text(f"✅ تم نشر {len(episodes)} حلقات بنجاح.")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()

        # التحقق من الاشتراك الإجباري
        try:
            member = await context.bot.get_chat_member(FORCE_CHANNEL, user_id)
            is_subscribed = member.status in ['member', 'administrator', 'creator']
        except:
            is_subscribed = False

        if not is_subscribed:
            msg = "⚠️ *يجب الاشتراك في القناة أولاً لمشاهدة الحلقة!*"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔔 اشترك هنا", url="https://t.me/+7AC_HNR8QFI5OWY0")]])
            
            # إصلاح مشكلة الصورة (Caption) مقابل النص (Text)
            try:
                if query.message.photo or query.message.caption:
                    await query.edit_message_caption(caption=msg, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
                else:
                    await query.edit_message_text(text=msg, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
            except BadRequest:
                pass # الرسالة لم تتغير
            return

        # معالجة المشاهدة
        if query.data.startswith("watch_"):
            ep_id = int(query.data.split("_")[1])
            with get_db() as db:
                ep = db.query(Episode).filter(Episode.id == ep_id).first()
                if ep:
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=ep.video_file_id,
                        caption=f"🎬 {ep.series_name} - حلقة {ep.episode_number}\n\nمشاهدة ممتعة!",
                        supports_streaming=True
                    )
                else:
                    await query.message.reply_text("❌ عذراً، الحلقة غير موجودة.")

    def run(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("post", self.post_command))
        self.application.add_handler(MessageHandler(filters.VIDEO | filters.FORWARDED, self.handle_forwarded_video))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        logger.info("🚀 البوت يعمل الآن بنجاح على Railway...")
        self.application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    bot = SeriesBot()
    bot.run()
