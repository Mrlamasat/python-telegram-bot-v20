# database.py
# نسخة وهمية للتجربة، لاحقًا يمكن ربط قاعدة بيانات حقيقية

episodes = []

def add_episode(title: str, link: str):
    """تضيف حلقة جديدة"""
    episodes.append({"title": title, "link": link})
    return True

def list_episodes():
    """ترجع كل الحلقات المخزنة"""
    return episodes
