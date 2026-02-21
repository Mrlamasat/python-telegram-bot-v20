import aiosqlite
import asyncio
import os

DB_PATH = "data/videos.db"

async def init_db():
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY,
            video_file_id TEXT,
            poster_file_id TEXT,
            title TEXT,
            duration INTEGER,
            quality TEXT,
            poster_group TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            subscribed INTEGER DEFAULT 0
        )
        """)
        await db.commit()

async def add_episode(video_file_id, poster_file_id, title, duration, quality, poster_group):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO episodes(video_file_id, poster_file_id, title, duration, quality, poster_group)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (video_file_id, poster_file_id, title, duration, quality, poster_group))
        await db.commit()

async def get_episodes_by_poster(poster_group):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM episodes WHERE poster_group=?", (poster_group,))
        rows = await cursor.fetchall()
        return rows

async def get_all_episodes():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM episodes ORDER BY id")
        rows = await cursor.fetchall()
        return rows
