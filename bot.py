# ==============================
# قاعدة البيانات - إنشاء الجداول والتأكد من عمود views
# ==============================
def init_db():
    # 1. إنشاء الجداول الأساسية إذا لم تكن موجودة
    db_query("""CREATE TABLE IF NOT EXISTS episodes (
        v_id TEXT PRIMARY KEY, 
        poster_id TEXT, 
        title TEXT, 
        ep_num INTEGER, 
        duration TEXT, 
        quality TEXT
    )""", commit=True)
    
    db_query("""CREATE TABLE IF NOT EXISTS temp_upload (
        chat_id BIGINT PRIMARY KEY, 
        v_id TEXT, 
        poster_id TEXT, 
        title TEXT, 
        ep_num INTEGER, 
        duration TEXT, 
        step TEXT
    )""", commit=True)
    
    # 2. التأكد من وجود عمود views
    ensure_views_column()


def ensure_views_column():
    """
    يتحقق من وجود عمود views في جدول episodes
    ويضيفه إذا لم يكن موجوداً
    """
    try:
        # تجربة الوصول للعمود
        db_query("SELECT views FROM episodes LIMIT 1", fetchone=True)
        logger.info("✅ عمود views موجود بالفعل")
    except Exception:
        logger.info("⚠️ عمود views غير موجود، جاري إنشاؤه...")
        db_query("ALTER TABLE episodes ADD COLUMN views INTEGER DEFAULT 0", commit=True)
        logger.info("✅ تم إنشاء عمود views بنجاح")
