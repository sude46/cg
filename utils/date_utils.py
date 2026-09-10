from datetime import datetime, timezone


def utcnow():
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)