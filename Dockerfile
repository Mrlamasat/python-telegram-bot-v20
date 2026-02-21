# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY bot.py .
COPY handlers ./handlers
COPY database.py .

RUN pip install --no-cache-dir -r requirements.txt

ENV BOT_TOKEN=""

CMD ["python", "bot.py"]
