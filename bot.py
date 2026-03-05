#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تليجرام لنشر المسلسلات مع قاعدة بيانات واشتراك إجباري
تم التطوير لنشر على Railway.app
"""

import os
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Tuple, List
from contextlib import contextmanager

# المكتبات المطلوبة
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# SQLAlchemy لقاعدة البيانات
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Text, Boolean, DateTime, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import NullPool

# ======================= الإعدادات =======================

# توكن البوت - تم التعديل
BOT_TOKEN = "8579897728:AAF_jh9HnSNdHfkVhrjVeeagsQmYh6Jfo"  # ✅ توكن البوت الخاص بك

# معرفات القنوات (أرقام وليس نصوص)
SOURCE_CHANNEL = -1003547072209      # القناة المصدر (فيها الحلقات)
TARGET_CHANNEL = -1003554018307      # قناة النشر النهائية
FORCE_CHANNEL = -1003894735143       # قناة الاشتراك الإجباري

# رابط قاعدة البيانات - Railway يوفر متغير DATABASE_URL تلقائياً
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///series_bot.db')

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================= قاعدة البيانات =======================

# تعديل رابط PostgreSQL ليعمل مع SQLAlchemy
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# إنشاء اتصال قاعدة البيانات
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    echo=False
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
    message_id = Column(BigInteger, unique=True, index=True)  # معرف الرسالة في القناة المصدر
    series_name = Column(String(500), index=True)             # اسم المسلسل
    episode_number = Column(Integer, default=0)               # رقم الحلقة
    episode_name = Column(String(500))                        # اسم الحلقة
    video_file_id = Column(String(500))                       # معرف الفيديو
    poster_file_id = Column(String(500), nullable=True)       # معرف الصورة (البوستر)
    quality = Column(String(50), default="HD")                # الجودة
    duration = Column(Integer, default=0)                      # المدة بالثواني
    caption = Column(Text, default="")                         # النص الأصلي
    created_at = Column(DateTime, default=datetime.utcnow)     # تاريخ الإضافة
    is_posted = Column(Boolean, default=False)                 # هل تم نشره في القناة المستهدفة
    posted_message_id = Column(BigInteger, nullable=True)      # معرف الرسالة بعد النشر

class User(Base):
    """جدول المستخدمين"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)     # معرف المستخدم
    username = Column(String(255), nullable=True)              # اسم المستخدم
    first_name = Column(String(255))                           # الاسم الأول
    joined_at = Column(DateTime, default=datetime.utcnow)      # تاريخ الانضمام
    last_used = Column(DateTime, default=datetime.utcnow)      # آخر استخدام

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
        raise e
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
        with get_db() as db:
            existing_user = db.query(User).filter(User.user_id == user.id).first()
            if not existing_user:
                new_user = User(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name or "مستخدم"
                )
                db.add(new_user)
                logger.info(f"👤 مستخدم جديد: {user.id} - {user.first_name}")
        
        # رسالة الترحيب
        welcome_text = (
            f"🎬 *مرحباً بك {user.first_name}!*\n\n"
            "أهلاً في بوت نشر المسلسلات\n\n"
            "*الأوامر المتاحة:*\n"
            "🔍 /scan - مسح القناة المصدر وجلب الحلقات\n"
            "📤 /post - نشر الحلقات الجديدة\n"
            "📊 /stats - عرض الإحصائيات\n"
            "❓ /help - عرض المساعدة\n\n"
            "✨ استمتع بمشاهدة مسلسلاتك المفضلة"
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
            "1️⃣ تأكد من إضافة البوت كمشرف في جميع القنوات\n"
            "2️⃣ استخدم /scan لمسح القناة المصدر مرة واحدة\n"
            "3️⃣ استخدم /post لنشر الحلقات في القناة المستهدفة\n"
            "4️⃣ المستخدمون يضغطون على زر المشاهدة للحصول على الحلقة\n\n"
            "*ملاحظات مهمة:*\n"
            "• يجب الاشتراك في القناة الإجبارية للمشاهدة\n"
            "• البوت يعمل تلقائياً على مدار الساعة\n"
            "• جميع الحلقات محفوظة في قاعدة البيانات"
        )
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /stats - عرض الإحصائيات"""
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
    
    async def scan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر /scan - مسح القناة المصدر"""
        status_msg = await update.message.reply_text("🔄 *جاري مسح القناة المصدر...*\n\n⏱ قد يستغرق هذا بضع دقائق", parse_mode=ParseMode.MARKDOWN)
        
        try:
            with get_db() as db:
                scanned = 0
                added = 0
                offset = 0
                limit = 100
                
                while True:
                    # جلب الرسائل من القناة
                    try:
                        messages = await context.bot.get_chat_history(
                            chat_id=SOURCE_CHANNEL,
                            limit=limit,
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
                        
                        # التحقق من وجود فيديو
                        if message.video:
                            # التحقق من عدم وجود الحلقة مسبقاً
                            existing = db.query(Episode).filter(Episode.message_id == message.message_id).first()
                            if not existing:
                                # استخراج المعلومات
                                series_name, episode_number, episode_name = self.extract_episode_info(message.caption or "")
                                
                                # البحث عن صورة مرفقة
                                poster_id = None
                                if message.photo:
                                    poster_id = message.photo[-1].file_id
                                
                                # تحديد الجودة
                                quality = self.detect_quality(message.video)
                                
                                # إنشاء حلقة جديدة
                                new_episode = Episode(
                                    message_id=message.message_id,
                                    series_name=series_name,
                                    episode_number=episode_number,
                                    episode_name=episode_name,
                                    video_file_id=message.video.file_id,
                                    poster_file_id=poster_id,
                                    quality=quality,
                                    duration=message.video.duration or 0,
                                    caption=message.caption or "",
                                    is_posted=False
                                )
                                db.add(new_episode)
                                added += 1
                                
                                # تحديث رسالة الحالة كل 10 حلقات
                                if added % 10 == 0:
                                    await status_msg.edit_text(
                                        f"🔄 *جاري المسح...*\n\n"
                                        f"📊 تم فحص: {scanned} رسالة\n"
                                        f"✅ تم العثور: {added} حلقة جديدة",
                                        parse_mode=ParseMode.MARKDOWN
                                    )
                        
                        offset = message.message_id
                    
                    await asyncio.sleep(1)  # تجنب تجاوز حدود السرعة
                
                db.commit()
                
            await status_msg.edit_text(
                f"✅ *تم المسح بنجاح!*\n\n"
                f"📊 *النتيجة:*\n"
                f"• تم فحص {scanned} رسالة\n"
                f"• تم العثور على {added} حلقة جديدة\n"
                f"• جميع الحلقات محفوظة في قاعدة البيانات",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"خطأ في المسح: {e}")
            await status_msg.edit_text(f"❌ حدث خطأ: {str(e)}")
    
    def extract_episode_info(self, caption: str) -> Tuple[str, int, str]:
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
                    episode_num = int(groups[1])
                except (ValueError, IndexError):
                    episode_num = 0
                
                episode_name = groups[2].strip() if len(groups) > 2 else f"الحلقة {episode_num}"
                
                # تنظيف النتائج
                series = re.sub(r'[\-_#]', ' ', series).strip()
                series = re.sub(r'\s+', ' ', series)
                
                return series, episode_num, episode_name
        
        # إذا لم يتم العثور على نمط
        return caption, 0, caption
    
    def detect_quality(self, video) -> str:
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
        status_msg = await update.message.reply_text("🔄 *جاري نشر الحلقات...*", parse_mode=ParseMode.MARKDOWN)
        
        try:
            with get_db() as db:
                # جلب 5 حلقات غير منشورة
                episodes = db.query(Episode).filter(
                    Episode.is_posted == False
                ).order_by(Episode.id).limit(5).all()
                
                if not episodes:
                    await status_msg.edit_text("✅ *لا توجد حلقات جديدة للنشر*", parse_mode=ParseMode.MARKDOWN)
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
                        
                        # إضافة حلقات مشابهة
                        similar = db.query(Episode).filter(
                            Episode.series_name == episode.series_name,
                            Episode.id != episode.id,
                            Episode.is_posted == True
                        ).order_by(Episode.episode_number).limit(6).all()
                        
                        if similar:
                            sim_buttons = []
                            for sim in similar:
                                sim_buttons.append(
                                    InlineKeyboardButton(f"📺 {sim.episode_number}", callback_data=f"watch_{sim.id}")
                                )
                            
                            # تقسيم الأزرار إلى صفوف من 3
                            for i in range(0, len(sim_buttons), 3):
                                keyboard.append(sim_buttons[i:i+3])
                            
                            keyboard.append([InlineKeyboardButton("🎯 جميع الحلقات", callback_data=f"series_{episode.series_name}")])
                        
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        # إرسال مع أو بدون بوستر
                        if episode.poster_file_id:
                            sent = await context.bot.send_photo(
                                chat_id=TARGET_CHANNEL,
                                photo=episode.poster_file_id,
                                caption=text,
                                reply_markup=reply_markup,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            sent = await context.bot.send_message(
                                chat_id=TARGET_CHANNEL,
                                text=text,
                                reply_markup=reply_markup,
                                parse_mode=ParseMode.MARKDOWN,
                                disable_web_page_preview=True
                            )
                        
                        # تحديث حالة الحلقة
                        episode.is_posted = True
                        episode.posted_message_id = sent.message_id
                        posted += 1
                        
                        await asyncio.sleep(2)  # تأخير بين المنشورات
                        
                    except Exception as e:
                        logger.error(f"خطأ في نشر الحلقة {episode.id}: {e}")
                        failed += 1
                
                db.commit()
                
            await status_msg.edit_text(
                f"✅ *تم النشر بنجاح!*\n\n"
                f"📊 *النتيجة:*\n"
                f"• تم نشر: {posted} حلقة\n"
                f"• فشل: {failed} حلقة\n"
                f"• المتبقي: {len(episodes) - posted} حلقة",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"خطأ في النشر: {e}")
            await status_msg.edit_text(f"❌ حدث خطأ: {str(e)}")
    
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
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                    # تحديث آخر استخدام للمستخدم
                    user = db.query(User).filter(User.user_id == user_id).first()
                    if user:
                        user.last_used = datetime.utcnow()
                        db.commit()
                    
                    # إرسال الفيديو
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=episode.video_file_id,
                        caption=f"🎬 {episode.series_name} - الحلقة {episode.episode_number}\n{episode.episode_name}",
                        supports_streaming=True
                    )
                    
                    # رسالة تأكيد
                    await query.edit_message_text(
                        f"✅ *تم إرسال الحلقة*\n\n"
                        f"🎬 {episode.series_name}\n"
                        f"📺 الحلقة {episode.episode_number}\n"
                        f"⚡ {episode.quality}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.edit_message_text("❌ عذراً، لم نتمكن من العثور على الحلقة")
        
        elif data.startswith("series_"):
            series_name = data.replace("series_", "", 1)
            
            with get_db() as db:
                episodes = db.query(Episode).filter(
                    Episode.series_name == series_name,
                    Episode.is_posted == True
                ).order_by(Episode.episode_number).limit(10).all()
                
                if episodes:
                    text = f"🎬 *{series_name}*\n\n📺 *الحلقات المتاحة:*\n"
                    keyboard = []
                    
                    for ep in episodes:
                        text += f"• الحلقة {ep.episode_number}: {ep.episode_name}\n"
                        keyboard.append([InlineKeyboardButton(
                            f"📺 الحلقة {ep.episode_number}", 
                            callback_data=f"watch_{ep.id}"
                        )])
                    
                    await query.edit_message_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
    
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
            self.application.add_handler(CommandHandler("scan", self.scan_command))
            self.application.add_handler(CommandHandler("post", self.post_command))
            
            # معالج الأزرار
            self.application.add_handler(CallbackQueryHandler(self.button_callback))
            
            # معالج الأخطاء
            self.application.add_error_handler(self.error_handler)
            
            # رسالة بدء التشغيل
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info(f"📊 القناة المصدر: {SOURCE_CHANNEL}")
            logger.info(f"📤 قناة النشر: {TARGET_CHANNEL}")
            logger.info(f"🔔 قناة الاشتراك: {FORCE_CHANNEL}")
            logger.info(f"🤖 توكن البوت: {BOT_TOKEN[:10]}...")
            
            # بدء البوت
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"❌ فشل تشغيل البوت: {e}")
            raise e

# ======================= نقطة البداية =======================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 بوت نشر المسلسلات - جاهز للتشغيل")
    print("=" * 50)
    print(f"🤖 توكن البوت: {BOT_TOKEN[:10]}...")
    print(f"📊 القناة المصدر: {SOURCE_CHANNEL}")
    print(f"📤 قناة النشر: {TARGET_CHANNEL}")
    print(f"🔔 قناة الاشتراك: {FORCE_CHANNEL}")
    print("=" * 50)
    
    # إنشاء وتشغيل البوت
    bot = SeriesBot()
    bot.run()
