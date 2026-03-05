# file: clear_database.py
import os
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)

# نفس إعدادات قاعدة البيانات من البوت
DATABASE_URL = os.environ.get("DATABASE_URL")

def clear_database():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        
        # حذف جميع البيانات من جدول videos
        cur.execute("DELETE FROM videos;")
        
        # إعادة تعيين عداد المشاهدات (اختياري)
        # cur.execute("ALTER SEQUENCE videos_id_seq RESTART WITH 1;")  # إذا كان هناك id
        
        conn.commit()
        count = cur.rowcount
        cur.close()
        conn.close()
        
        logging.info(f"✅ تم مسح {count} سجل من قاعدة البيانات")
        return count
    except Exception as e:
        logging.error(f"❌ خطأ في مسح قاعدة البيانات: {e}")
        return None

if __name__ == "__main__":
    confirm = input("هل أنت متأكد من مسح جميع البيانات؟ (yes/no): ")
    if confirm.lower() == "yes":
        clear_database()
        print("✅ تم مسح قاعدة البيانات بنجاح")
    else:
        print("❌ تم الإلغاء")
