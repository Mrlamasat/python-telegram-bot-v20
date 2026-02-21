import sqlite3

def init_db():
    conn = sqlite3.connect("bot.db")
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS likes (
        video_id TEXT,
        user_id INTEGER,
        UNIQUE(video_id, user_id)
    )
    """)

    conn.commit()
    conn.close()

def execute(query, params=(), fetch=False):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    result = cursor.fetchall() if fetch else None
    conn.close()
    return result
