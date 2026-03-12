import psycopg2
import logging
import time
from config import DATABASE_URL

def db_query(query, params=(), fetch=True, retry=3):
    """دالة موحدة للتعامل مع قاعدة البيانات"""
    for attempt in range(retry):
        try:
            conn = psycopg2.connect(DATABASE_URL, sslmode="require")
            cur = conn.cursor()
            cur.execute(query, params)
            res = cur.fetchall() if fetch else None
            conn.commit()
            cur.close()
            conn.close()
            return res
        except Exception as e:
            logging.error(f"DB Error (attempt {attempt+1}): {e}")
            if attempt == retry - 1:
                return [] if fetch else None
            time.sleep(1)

def init_database():
    """إنشاء جميع الجداول المطلوبة"""
    db_query("CREATE TABLE IF NOT EXISTS videos (v_id TEXT PRIMARY KEY, series_name TEXT, ep_num INTEGER DEFAULT 0, quality TEXT DEFAULT 'HD', views INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS posters (poster_id BIGINT PRIMARY KEY, series_name TEXT, video_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, user_id BIGINT UNIQUE, username TEXT, first_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS pending_posts (video_id TEXT PRIMARY KEY, step TEXT, poster_id BIGINT, quality TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    db_query("CREATE TABLE IF NOT EXISTS views_log (id SERIAL PRIMARY KEY, v_id TEXT, viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)", fetch=False)
    print("✅ قاعدة البيانات جاهزة")
