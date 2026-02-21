def format_duration(seconds: int) -> str:
    if not seconds:
        return "غير محدد"
    mins, secs = divmod(seconds, 60)
    return f"{mins}:{secs:02d} دقيقة"
