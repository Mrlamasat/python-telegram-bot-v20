import os
import sqlite3

# مسار قاعدة البيانات داخل الحاوية
DB_DIR = "/app/data"
DB_PATH = os.path.join(DB_DIR, "videos.db")

def init_db():
    # إنشاء المجلد لو لم يكن موجودًا
    os.makedirs(DB_DIR, exist_ok=True)

    try:
        # الاتصال بقاعدة البيانات
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # إنشاء جدول الفيديوهات لو لم يكن موجودًا
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

    except sqlite3.Error as e:
        print(f"[ERROR] SQLite error: {e}")
        raise
