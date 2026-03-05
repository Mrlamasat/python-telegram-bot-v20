#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- الإعدادات ---
BOT_TOKEN = "8579897728:AAHrgUVKh0D45SMa0iHYI-DkbuWxeYm-rns"
SOURCE_CHANNEL = -1003547072209
TARGET_CHANNEL = -1003554018307
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# حالات المحادثة
VIDEO, PHOTO, SERIES_NAME, QUALITY, EP_NUMBER = range(5)

# --- إعداد قاعدة البيانات ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Episode(Base):
    __tablename__ = 'episodes_new'  # تغيير الاسم لضمان إنشاء جدول نظيف بهيكلية صحيحة
    id = Column(Integer, primary_key=True)
    message_id = Column(BigInteger, nullable=True) # العمود الذي كان يسبب المشكلة
    series_name = Column(String(500))
    episode_number = Column(Integer)
    video_id = Column(String(500))
    photo_id = Column(String(500), nullable=True)
    quality = Column(String(50))
    posted = Column(Boolean, default=False)

# إنشاء الجداول الجديدة
Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- الدالات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # تصفير بيانات المستخدم عند البدء من جديد
    context.user_data.clear()
    await update.message.reply_text("🎬 أهلاً بك! لرفع حلقة، أرسل الفيديو الآن.")
    return VIDEO

async def get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if not video:
        await update.message.reply_text("⚠️ يرجى إرسال فيديو.")
        return VIDEO

    context.user_data['video_id'] = video.file_id
    context.user_data['message_id'] = update.message.forward_from_message_id or update.message.message_id
    
    await update.message.reply_text("✅ تم استلام الفيديو. أرسل الآن **البوستر** أو /skip:")
    return PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['photo_id'] = update.message.photo[-1].file_id
    else:
        context.user_data['photo_id'] = None
    
    await update.message.reply_text("📝 أرسل **اسم المسلسل**:")
    return SERIES_NAME

async def get_series_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['series_name'] = update.message.text
    keyboard = [["4K", "Full HD"], ["HD", "SD"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("🎬 اختر **الجودة**:", reply_markup=reply_markup)
    return QUALITY

async def get_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['quality'] = update.message.text
    await update.message.reply_text("🔢 أرسل **رقم الحلقة**:")
    return EP_NUMBER

async def finalize_and_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ أرسل رقماً فقط:")
        return EP_NUMBER

    data = context.user_data
    db = SessionLocal()
    try:
        new_ep = Episode(
            series_name=data['series_name'],
            episode_number=int(update.message.text),
            video_id=data['video_id'],
            photo_id=data['photo_id'],
            quality=data['quality'],
            message_id=data.get('message_id'),
            posted=True
        )
        db.add(new_ep)
        db.commit()
        
        # رابط المشاهدة
        bot_user = await context.bot.get_me()
        watch_link = f"https://t.me/{bot_user.username}?start=watch_{new_ep.id}"
        
        caption = f"🎬 *{data['series_name']}*\n📺 *الحلقة: {update.message.text}*\n⚡ *الجودة: {data['quality']}*"
        keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", url=watch_link)]]
        
        if data['photo_id']:
            await context.bot.send_photo(chat_id=TARGET_CHANNEL, photo=data['photo_id'], caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_message(chat_id=TARGET_CHANNEL, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

        await update.message.reply_text(f"✅ تم النشر! الرابط: {watch_link}")
    except Exception as e:
        logger.error(f"Error saving: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء الحفظ.")
    finally:
        db.close()
    
    return ConversationHandler.END

# --- تشغيل البوت ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.VIDEO, get_video)
        ],
        states={
            VIDEO: [MessageHandler(filters.VIDEO, get_video)],
            PHOTO: [MessageHandler(filters.PHOTO), CommandHandler("skip", get_photo)],
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
