# Dockerfile

# نبدأ بصورة Python الرسمية
FROM python:3.11-slim

# إعداد مجلد العمل
WORKDIR /app

# نسخ ملفات المشروع
COPY requirements.txt .
COPY bot.py .
COPY handlers ./handlers
COPY database.py .

# تثبيت المتطلبات
RUN pip install --no-cache-dir -r requirements.txt

# تعريف المتغيرات البيئية الافتراضية (يمكن تعديلها في الاستضافة)
ENV BOT_TOKEN=""

# تشغيل البوت عند بدء الحاوية
CMD ["python", "bot.py"]
