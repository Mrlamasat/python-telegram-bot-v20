import sqlite3
from config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS videos(
        video_id TEXT PRIMARY KEY,
        file_id TEXT,
        poster_id TEXT,
        title TEXT,
        episode INTEGER,
        quality TEXT,
        duration TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS likes(
        video_id TEXT,
        user_id INTEGER,
        UNIQUE(video_id, user_id)
    )
    """)
    conn.commit()
    conn.close()

def db(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    data = cur.fetchall() if fetch else None
    conn.close()
    return data
