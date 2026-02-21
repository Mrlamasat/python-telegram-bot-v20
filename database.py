import sqlite3
import os

DB_PATH = "/app/data/videos.db"

def init_db():
    # تأكد من وجود المجلد
    os.makedirs("/app/data", exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # إنشاء جدول videos إذا لم يكن موجوداً
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            file_id TEXT,
            poster_id TEXT,
            title TEXT,
            episode INTEGER,
            quality TEXT,
            duration TEXT
        )
    """)
    conn.commit()
    conn.close()
    print(f"[INFO] Database initialized at {DB_PATH}")
