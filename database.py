import sqlite3

# إنشاء قاعدة البيانات والجدول إذا لم يكن موجود
conn = sqlite3.connect('episodes.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    link TEXT NOT NULL
)
''')
conn.commit()

def add_episode(title, link):
    cursor.execute('INSERT INTO episodes (title, link) VALUES (?, ?)', (title, link))
    conn.commit()

def list_episodes():
    cursor.execute('SELECT title, link FROM episodes')
    return cursor.fetchall()
