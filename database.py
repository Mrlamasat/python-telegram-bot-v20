import sqlite3
import os

DB_FILE = os.environ.get("DATABASE_FILE", "episodes.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# إضافة حلقة
def add_episode(title, link):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO episodes (title, link) VALUES (?, ?)", (title, link))
    conn.commit()
    conn.close()

# جلب جميع الحلقات
def list_episodes():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT title, link FROM episodes")
    rows = cursor.fetchall()
    conn.close()
    return [{"title": r[0], "link": r[1]} for r in rows]

# إنشاء قاعدة البيانات عند استيراد الملف
init_db()
