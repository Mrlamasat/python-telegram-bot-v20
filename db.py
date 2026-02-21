import sqlite3

DB_FILE = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            v_id TEXT PRIMARY KEY,
            duration TEXT,
            poster_id TEXT,
            status TEXT,
            ep_num INTEGER,
            quality TEXT,
            title TEXT
        )
    ''')
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetch=True):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    res = cursor.fetchall() if fetch else None
    conn.close()
    return res

init_db()
