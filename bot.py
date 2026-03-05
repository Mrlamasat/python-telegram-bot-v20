#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
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
TARGET_CHANNEL = -1003554018307
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# حالات المحادثة
VIDEO, PHOTO, SERIES_NAME, QUALITY, EP_NUMBER = range(5)

# --- قاعدة البيانات ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Episode(Base):
    __tablename__ = 'episodes'
    id = Column(Integer, primary_key=True)
    series_name = Column(String(500))
    episode_number = Column(Integer)
    video_id = Column(String(500))
    photo_id = Column(String(500))
    quality = Column(String(50))
    posted = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- دالات البوت ---

async def start_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 بدأت عملية الرفع.. أرسل **مقطع الفيديو** الآن (أو قم بتوجيهه):")
    return VIDEO

async def get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.video:
        await update.message.reply_text("❌ يرجى إرسال فيديو فقط.")
        return VIDEO
    context.user_data['video_id'] = update.message.video.file_id
    await update.message.reply_text("✅ تم استلام الفيديو. الآن أرسل **صورة البوستر** (أو أرسل /skip إذا لا يوجد):")
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
    
    await update.message.reply_text("🎬 اختر **جودة الحلقة** من القائمة:", reply_markup=reply_markup)
    return QUALITY

async def get_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['quality'] = update.message.text
    await update.message.reply_text("🔢 أخيراً، أرسل **رقم الحلقة**:", reply_markup=ReplyKeyboardRemove())
    return EP_NUMBER

async def finalize_and_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ep_num = int(update.message.text)
        data = context.user_data
        
        # حفظ في قاعدة البيانات
        db = SessionLocal()
        new_ep = Episode(
            series_name=data['series_name'],
            episode_number=ep_num,
            video_id=data['video_id'],
            photo_id=data['photo_id'],
            quality=data['quality'],
            posted=True
        )
        db.add(new_ep)
        db.commit()
        db.close()

        # النشر التلقائي في القناة
        caption = (
            f"🎬 *{data['series_name']}*\n"
            f"📺 *الحلقة: {ep_num}*\n"
            f"⚡ *الجودة: {data['quality']}*\n\n"
            f"📥 تم رفع الحلقة بنجاح للمشاهدة."
        )
        
        keyboard = [[InlineKeyboardButton("▶️ مشاهدة الآن", url=f"https://t.me/{(await context.bot.get_me()).username}?start=watch_{new_ep.id}")]]
        
        if data['photo_id']:
            await context.bot.send_photo(chat_id=TARGET_CHANNEL, photo=data['photo_id'], caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_message(chat_id=TARGET_CHANNEL, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

        await update.message.reply_text(f"✅ تم النشر بنجاح في القناة! \nالمسلسل: {data['series_name']} - حلقة {ep_num}")
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ يرجى إرسال رقم صحيح للحلقة.")
        return EP_NUMBER

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- التشغيل ---

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("upload", start_upload), MessageHandler(filters.VIDEO, get_video)],
        states={
            VIDEO: [MessageHandler(filters.VIDEO, get_video)],
            PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, get_photo), CommandHandler("skip", get_photo)],
            SERIES_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_series_name)],
            QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_quality)],
            EP_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_and_post)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    
    print("🚀 البوت يعمل بنظام الخطوات.. أرسل فيديو للبدء.")
    app.run_polling()

if __name__ == "__main__":
    main()
