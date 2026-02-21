# database.py
import aiosqlite

DB_PATH = "data/videos.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            poster TEXT,
            video_file_id TEXT,
            quality TEXT,
            episode_number INTEGER
        )
        """)
        await db.commit()

async def add_episode(title, poster, video_file_id, quality, episode_number):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO episodes (title, poster, video_file_id, quality, episode_number) VALUES (?, ?, ?, ?, ?)",
            (title, poster, video_file_id, quality, episode_number)
        )
        await db.commit()
