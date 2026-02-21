import sqlite3
import os

DB_PATH = "data/videos.db"

def init_db():
    os.makedirs("data", exist_ok=True)  # تأكد من وجود مجلد البيانات
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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

def execute(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()
