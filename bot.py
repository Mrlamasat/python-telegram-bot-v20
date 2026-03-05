#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import re
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from telegram.constants import ParseMode
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Text, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- الإعدادات (تأكد من صحة معرفات القنوات) ---
BOT_TOKEN = "8579897728:AAHrgUVKh0D45SMa0iHYI-DkbuWxeYm-rns"
SOURCE_CHANNEL = -1003547072209      # القناة المصدر (للأرشفة)
TARGET_CHANNEL = -1003554018307      # قناة النشر
FORCE_CHANNEL = -1003894735143       # قناة الاشتراك الإجباري
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# حالات المحادثة
VIDEO, PHOTO, SERIES_NAME, QUALITY, EP_NUMBER = range(5)

# --- إعداد قاعدة البيانات ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Episode(Base):
    __tablename__ = 'episodes'
    id = Column(Integer, primary_key=True)
    message_id = Column(BigInteger, nullable=True) 
    series_name = Column(String(500))
    episode_number = Column(Integer)
    video_id = Column(String(500))
    photo_id = Column(String(500), nullable=True)
    quality = Column(String(50))
    posted = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- وظيفة جلب الأرشيف والترحيب ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            f"🎬 مرحباً بك يا {update.effective_user.first_name} في بوت المسلسلات.\n\n"
            "• لرفع حلقة جديدة أرسل مقطع الفيديو فوراً.\n"
            "• للمساعدة أرسل /help"
        )
        return

    # نظام الروابط القديمة والجلب من المصدر
    if args[0].startswith("watch_"):
        ep_id = args[0].replace("watch_", "")
        db = SessionLocal()
        episode = db.query(Episode).filter(Episode.id == int(ep_id)).first()
        
        try:
            if episode:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=episode.video_id,
                    caption=f"🎬 {episode.series_name}\n📺 الحلقة: {episode.episode_number}\n⚡ الجودة: {episode.quality}",
                    supports_streaming=True
                )
            else:
                # محاولة الجلب المباشر من القناة المصدر (للأرشفة القديمة)
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=SOURCE_CHANNEL,
                    message_id=int(ep_id),
                    caption="✅ تم جلب الحلقة من الأرشيف بنجاح!"
                )
        except Exception as e:
            await update.message.reply_text("❌ عذراً، لم يتم العثور على هذه الحلقة أو تم حذفها.")
        finally:
            db.close()

# --- نظام الرفع المتسلسل الجديد ---
async def start_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 أرسل **مقطع الفيديو** الآن (أو قم بتوجيهه):")
    return VIDEO

async def get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.video:
        await update.message.reply_text("❌ يرجى إرسال فيديو فقط.")
        return VIDEO
    
    context.user_data['video_id'] = update.message.video.file_id
    context.user_data['orig_msg_id'] = update.message.forward_from_message_id or update.message.message_id
    
    await update.message.reply_text("✅ تم استلام الفيديو. الآن أرسل **صورة البوستر** (أو أرسل /skip):")
    return PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['photo_id'] = update.message.photo[-1].file_id
    else:
        context.user_data['photo_id'] = None
    
    await update.message.reply_text("📝 ممتاز، الآن أرسل **اسم المسلسل**:")
    return SERIES_NAME

async def get_series_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['series_name'] = update.message.text
    keyboard = [["4K", "Full HD"], ["HD", "SD"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("🎬 اختر **جودة الحلقة**:", reply_markup=reply_markup)
    return QUALITY

async def get_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['quality'] = update.message.text
    await update.message.reply_text("🔢 أخيراً، أرسل **رقم الحلقة**:", reply_markup=ReplyKeyboardRemove())
    return EP_NUMBER

async def finalize_and_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ep_num = int(update.message.text)
        data = context.user_data
        
        db = SessionLocal()
        new_ep = Episode(
            series_name=data['series_name'],
            episode_number=ep_num,
            video_id=data['video_id'],
            photo_id=data['photo_id'],
            quality=data['quality'],
            message_id=data['orig_msg_id'],
            posted=True
        )
        db.add(new_ep)
        db.commit()
        
        # إنشاء رابط المشاهدة
        bot_info = await context.bot.get_me()
        watch_link = f"https://t.me/{bot_info.username}?start=watch_{new_ep.id}"
        
        caption = (
            f"🎬 *{data['series_name']}*\n"
            f"📺 *الحلقة: {ep_num}*\n"
            f"⚡ *الجودة: {data['quality']}*\n\n"
            f"👇 اضغط على الزر أدناه للمشاهدة"
        )
        
        keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", url=watch_link)]]
        
        if data['photo_id']:
            await context.bot.send_photo(chat_id=TARGET_CHANNEL, photo=data['photo_id'], caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_message(chat_id=TARGET_CHANNEL, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

        await update.message.reply_text(f"✅ تم الحفظ والنشر بنجاح!")
        db.close()
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ يرجى إرسال رقم صحيح للحلقة.")
        return EP_NUMBER

# --- تشغيل البوت ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # معالج المحادثة للرفع
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("upload", start_upload),
            MessageHandler(filters.VIDEO & ~filters.COMMAND, get_video)
        ],
        states={
            VIDEO: [MessageHandler(filters.VIDEO, get_video)],
            PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, get_photo), CommandHandler("skip", get_photo)],
            SERIES_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_series_name)],
            QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_quality)],
            EP_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_and_post)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    
    print("🚀 البوت يعمل الآن.. بانتظار الفيديوهات.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
