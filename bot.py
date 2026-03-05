#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- الإعدادات ---
BOT_TOKEN = "8579897728:AAHrgUVKh0D45SMa0iHYI-DkbuWxeYm-rns"
SOURCE_CHANNEL = -1003547072209  # القناة المصدر (المخزن)
TARGET_CHANNEL = -1003554018307  # قناة النشر العامة
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"

# --- قاعدة البيانات ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Episode(Base):
    __tablename__ = 'smart_archive'
    id = Column(Integer, primary_key=True)
    message_id = Column(BigInteger, unique=True) # رقم الرسالة في القناة المصدر
    video_id = Column(String(500))
    series_name = Column(String(500), default="أرشيف قديم")
    episode_number = Column(Integer, default=0)

Base.metadata.create_all(bind=engine)
logging.basicConfig(level=logging.INFO)

# --- منطق الذكاء والأرشفة ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("🎬 أهلاً بك! أنا بوت الأرشفة الذكي. ارفع أي فيديو لأقوم بنشره وأرشفته.")
        return

    # معالجة الضغط على رابط (t.me/bot?start=watch_123)
    if args[0].startswith("watch_"):
        msg_id_str = args[0].replace("watch_", "")
        if not msg_id_str.isdigit(): return
        
        target_msg_id = int(msg_id_str)
        db = SessionLocal()
        
        # 1. البحث في الأرشيف الجديد (قاعدة البيانات)
        episode = db.query(Episode).filter(Episode.message_id == target_msg_id).first()
        
        if episode:
            # تم العثور عليها في الأرشيف - إرسال سريع
            await context.bot.send_video(
                chat_id=user_id,
                video=episode.video_id,
                caption=f"✅ تم جلبها من الأرشيف الذكي\n🎬 {episode.series_name} - حلقة {episode.episode_number}"
            )
        else:
            # 2. لم يتم العثور عليها (رابط قديم) - جلب مباشر من المصدر + أرشفة فورية
            try:
                # جلب (نسخ) الرسالة من القناة المصدر
                copied_msg = await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=SOURCE_CHANNEL,
                    message_id=target_msg_id
                )
                
                # التحقق إذا كانت الرسالة تحتوي على فيديو لأرشفته
                if copied_msg and (await context.bot.get_message(user_id, copied_msg.message_id)).video:
                    video_file_id = (await context.bot.get_message(user_id, copied_msg.message_id)).video.file_id
                    
                    # أرشفة ذكية الآن لكي لا يضطر البوت لجلبها من المصدر مرة أخرى
                    new_archive = Episode(
                        message_id=target_msg_id,
                        video_id=video_file_id
                    )
                    db.add(new_archive)
                    db.commit()
                    logging.info(f"📦 تمت أرشفة الحلقة {target_msg_id} تلقائياً عند طلب المستخدم.")
            
            except Exception as e:
                await update.message.reply_text("❌ نعتذر، هذه الحلقة قديمة جداً ولم تعد موجودة في القناة المصدر.")
        
        db.close()

# --- وظيفة الرفع والنشر الجديد ---

async def handle_new_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.video: return
    
    video = update.message.video
    # استخدام رقم الرسالة في القناة المصدر كـ ID دائم
    source_msg_id = update.message.forward_from_message_id or update.message.message_id
    
    db = SessionLocal()
    # أرشفة
    new_ep = Episode(
        message_id=source_msg_id,
        video_id=video.file_id
    )
    db.add(new_ep)
    db.commit()
    
    # رابط المشاهدة الذكي
    bot_username = (await context.bot.get_me()).username
    watch_link = f"https://t.me/{bot_username}?start=watch_{source_msg_id}"
    
    # نشر في قناة الأعضاء
    keyboard = [[InlineKeyboardButton("▶️ مشاهدة الحلقة", url=watch_link)]]
    await context.bot.send_message(
        chat_id=TARGET_CHANNEL,
        text=f"🎬 حلقة جديدة جاهزة للمشاهدة!\n\nاضغط على الزر أدناه 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await update.message.reply_text(f"✅ تمت الأرشفة والنشر بنجاح.\nرابط المشاهدة: {watch_link}")
    db.close()

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO, handle_new_upload))
    app.run_polling()

if __name__ == "__main__":
    main()
