import logging
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from config import FORCE_SUB_CHANNEL, FORCE_SUB_LINK, ADMIN_ID

async def check_force_sub(client, user_id):
    """التحقق من اشتراك المستخدم في القناة الإجبارية"""
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception as e:
        logging.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

async def get_force_sub_button():
    """زر الاشتراك في القناة"""
    return InlineKeyboardButton(
        "🔔 اشترك في القناة أولاً", 
        url=FORCE_SUB_LINK
    )

def get_backup_channel_button():
    """زر القناة الاحتياطية (نفس القناة الإجبارية)"""
    return InlineKeyboardButton(
        "🔗 القناة الاحتياطية", 
        url=FORCE_SUB_LINK
    )

def register_force_sub_commands(app):
    """تسجيل أوامر الاشتراك الإجباري"""
    
    @app.on_message(filters.command("test_force") & filters.user(ADMIN_ID))
    async def test_force(client, message):
        """اختبار صلاحيات البوت في القناة الإجبارية"""
        try:
            channel = await client.get_chat(FORCE_SUB_CHANNEL)
            try:
                bot_member = await client.get_chat_member(FORCE_SUB_CHANNEL, "me")
                bot_status = bot_member.status
                if bot_status == ChatMemberStatus.ADMINISTRATOR:
                    status_str = "ADMINISTRATOR (مشرف)"
                elif bot_status == ChatMemberStatus.MEMBER:
                    status_str = "MEMBER (عضو)"
                elif bot_status == ChatMemberStatus.OWNER:
                    status_str = "OWNER (مالك)"
                else:
                    status_str = str(bot_status)
            except Exception as e:
                status_str = f"❌ خطأ: {e}"
            
            text = f"📊 **معلومات القناة الإجبارية**\n\n"
            text += f"اسم القناة: {channel.title}\n"
            text += f"معرف القناة: `{FORCE_SUB_CHANNEL}`\n"
            text += f"حالة البوت: {status_str}\n\n"
            
            if bot_status == ChatMemberStatus.ADMINISTRATOR:
                text += "✅ البوت مشرف - يمكنه التحقق من الاشتراكات"
            elif bot_status == ChatMemberStatus.MEMBER:
                text += "⚠️ البوت عضو فقط - يحتاج صلاحية مشرف للتحقق من الاشتراكات"
            else:
                text += "❌ البوت ليس مشرفاً - أضفه كمشرف مع صلاحية مشاهدة الرسائل"
            
            await message.reply_text(text)
            
        except Exception as e:
            await message.reply_text(f"❌ خطأ في فحص القناة: {e}")
