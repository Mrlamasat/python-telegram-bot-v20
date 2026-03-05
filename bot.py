#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import re
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

# --- الإعدادات ---
BOT_TOKEN = "8579897728:AAF_jh9HnSNdHfkVhrjVeeagsQmYh6Jfo"
SOURCE_CHANNEL = -1003547072209      # القناة المصدر (للأرشفة)
TARGET_CHANNEL = -1003554018307      # قناة النشر
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# حالات المحادثة للرفع الجديد
VIDEO, PHOTO, SERIES_NAME, QUALITY, EP_NUMBER = range(5)

# --- قاعدة البيانات ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Episode(Base):
    __tablename__ = 'episodes'
    id = Column(Integer, primary_key=True)
    message_id = Column(BigInteger, nullable=True) # رقم الرسالة في المصدر للأرشفة
    series_name = Column(String(500))
    episode_number = Column(Integer)
    video_id = Column(String(500))
    photo_id = Column(String(500), nullable=True)
    quality = Column(String(50))
    posted = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- وظيفة جلب الأرشيف (الروابط القديمة) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args # فحص إذا كان الرابط يحتوي على watch_ID
    
    # رسالة الترحيب العادية إذا لم يكن هناك رابط
    if not args:
        await update.message.reply_text(
            f"🎬 مرحباً بك يا {update.effective_user.first_name}\n"
            "أنا بوت أرشفة ونشر المسلسلات. أرسل فيديو للبدء بالرفع."
        )
        return

    # إذا كان المستخدم ضغط على رابط مشاهدة (watch_123)
    if args[0].startswith("watch_"):
        ep_id = args[0].replace("watch_", "")
        db = SessionLocal()
        episode = db.query(Episode).filter(Episode.id == int(ep_id)).first()
        
        if episode:
            # الحلقة موجودة في القاعدة الجديدة
            await context.bot.send_video(
                chat_id=user_id,
                video=episode.video_id,
                caption=f"🎬 {episode.series_name}\n📺 الحلقة: {episode.episode_number}\n⚡ الجودة: {episode.quality}",
                supports_streaming=True
            )
        else:
            # محاولة جلبها من القناة المصدر إذا كانت قديمة جداً
            # ملاحظة: يجب أن يكون ID الحلقة هو نفسه ID الرسالة في المصدر ليعمل هذا المنطق تلقائياً
            try:
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=SOURCE_CHANNEL,
                    message_id=int(ep_id), # نفترض أن الروابط القديمة تستخدم ID الرسالة
                    caption="✅ تم جلب الحلقة من الأرشيف بنجاح!"
                )
            except Exception as e:
                await update.message.reply_text("❌ عذراً، هذه الحلقة قديمة جداً أو تم حذفها من المصدر.")
        db.close()

# --- نظام الرفع المتسلسل (الجديد) ---

async def start_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 أرسل **مقطع الفيديو** الآن:")
    return VIDEO

async def get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['video_id'] = update.message.video.file_id
    context.user_data['orig_msg_id'] = update.message.forward_from_message_id or update.message.message_id
    await update.message.reply_text("✅ تم. الآن أرسل **صورة البوستر** (أو /skip):")
    return PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['photo_id'] = update.message.photo[-1].file_id if update.message.photo else None
    await update.message.reply_text("📝 أرسل **اسم المسلسل**:")
    return SERIES_NAME

async def get_series_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['series_name'] = update.message.text
    keyboard = [["4K", "Full HD"], ["HD", "SD"]]
    await update.message.reply_text("🎬 اختر **الجودة**:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return QUALITY

async def get_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['quality'] = update.message.text
    await update.message.reply_text("🔢 أرسل **رقم الحلقة**:", reply_markup=ReplyKeyboardRemove())
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
        
        # رابط المشاهدة المعتمد على ID قاعدة البيانات
        watch_link = f"https://t.me/{(await context.bot.get_me()).username}?start=watch_{new_ep.id}"
        
        caption = f"🎬 *{data['series_name']}*\n📺 *الحلقة: {ep_num}*\n⚡ *الجودة: {data['quality']}*"
        keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", url=watch_link)]]
        
        if data['photo_id']:
            await context.bot.send_photo(chat_id=TARGET_CHANNEL, photo=data['photo_id'], caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_message(chat_id=TARGET_CHANNEL, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

        await update.message.reply_text(f"✅ تم النشر بنجاح!")
        db.close()
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ أرسل رقماً صحيحاً.")
        return EP_NUMBER

# --- تشغيل البوت ---

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # معالج الروابط (بدء التشغيل والجلب)
    app.add_handler(CommandHandler("start", start))

    # معالج الرفع
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("upload", start_upload), MessageHandler(filters.VIDEO, get_video)],
        states={
            VIDEO: [MessageHandler(filters.VIDEO, get_video)],
            PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, get_photo), CommandHandler("skip", get_photo)],
            SERIES_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_series_name)],
            QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_quality)],
            EP_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_and_post)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
