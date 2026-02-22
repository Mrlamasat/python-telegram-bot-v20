import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from pyrogram import Client, filters

# --- الإعدادات (نفس بياناتك في Termux) ---
SESSION_STRING = "BAIcPawApJ69F_MuL6ZdUOl46dOA4NXG4MgQJDS3axRjkssKYSV9ltkhPRTQElot9VkNpJvL3qQKLyoY7NlCXmro5NzcN27iPtec9rNTBNgCLfrb3CcpWwZm-TQX2CKDeC-abxVgg8OplS8b3oJhp5_xtYyk_6JNF-JeAwMuRPzseKT4jByOM8Yq5LZN2N5m3FDVrhu-gUjskn6iQZkoX63pkPRMy-Nyf8OMQnruDmSnWuEchkimIn3Env_GiHp-o2M514pZzSFrDvkxtUfjNtv1TLrnJ7R8pUyCHlOEbQA08BYSlluv8CopcQNQjz3ajK6GxVsUiYdbA8QyWM27HgrCCdASOAAAAAHMKGDXAA"
DATABASE_URL = "postgresql://postgres:TqPdcmimgOlWaFxqtRnJGFuFjLQiTFxZ@hopper.proxy.rlwy.net:31841/railway"
CHANNEL_USERNAME = "@Ramadan4kTV"

# تشغيل الحساب كـ Userbot (مثل Termux تماماً)
app = Client(
    "mo_user_bot", 
    session_string=SESSION_STRING, 
    api_id=35405228, 
    api_hash="dacba460d875d963bbd4462c5eb554d6",
    sleep_threshold=60
)

def encrypt_text(text):
    return "•".join(list(text)) if text else ""

def db_query(query, params=(), commit=False):
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        cur.execute(query, params)
        if commit: conn.commit()
        cur.close()
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        if conn: conn.close()

# 1. مراقبة القناة وسحب الحلقات تلقائياً
@app.on_message(filters.chat(CHANNEL_USERNAME) & filters.video)
async def handle_new_video(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    db_query("INSERT INTO episodes (v_id, title) VALUES (%s, %s) ON CONFLICT (v_id) DO UPDATE SET title=EXCLUDED.title", (v_id, safe_title), commit=True)
    print(f"📥 تم سحب حلقة جديدة تلقائياً: {v_id}")

# 2. مراقبة تعديل الأسماء في القناة
@app.on_edited_message(filters.chat(CHANNEL_USERNAME) & filters.video)
async def handle_edit(client, message):
    v_id = str(message.id)
    safe_title = encrypt_text(message.caption or f"فيديو {v_id}")
    db_query("UPDATE episodes SET title=%s WHERE v_id=%s", (safe_title, v_id), commit=True)
    print(f"🔐 تم تحديث اسم الحلقة: {v_id}")

# 3. نظام البحث الصامت (بدون ردود مكررة)
@app.on_message(filters.private & filters.text & ~filters.me & ~filters.outgoing)
async def search_bot(client, message):
    txt = message.text.strip()
    if len(txt) < 2: return 
    
    search_query = f"%{encrypt_text(txt)}%"
    # جلب النتائج من قاعدة البيانات
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT v_id FROM episodes WHERE title ILIKE %s LIMIT 5", (search_query,))
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    if results:
        for res in results:
            try:
                # إرسال الفيديو من القناة للمستخدم
                await app.copy_message(
                    chat_id=message.chat.id, 
                    from_chat_id=CHANNEL_USERNAME, 
                    message_id=int(res['v_id'])
                )
                await asyncio.sleep(1)
            except: pass

print("🚀 نظام السحب التلقائي (Userbot) يعمل الآن على الاستضافة...")
app.run()
