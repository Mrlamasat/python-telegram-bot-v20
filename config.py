import os
from dotenv import load_dotenv

load_dotenv()

# توكن البوت
BOT_TOKEN = os.getenv("BOT_TOKEN", "8579897728:AAHCeFONuRJca-Y1iwq9bV7OK8RQotldzr0")

# قناة التخزين الخاصة بالمشرفين
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", -1003547072209))

# القناة العامة للنشر
PUBLIC_CHANNEL_ID = os.getenv("PUBLIC_CHANNEL_ID", "RamadanSeries26")

# قناة الاشتراك الإجباري للمستخدمين
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "MoAlmohsen")

# معرفات المشرفين (يمكنك إضافة أكثر من معرف مفصول بفاصلة)
ADMINS = list(map(int, os.getenv("ADMINS", "7720165591").split(",")))

# مسار قاعدة البيانات (Railway يستخدم /data/ للمساحات الدائمة)
DB_PATH = os.getenv("DB_PATH", "/data/bot_data.db")
