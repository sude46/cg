from datetime import UTC, datetime


def utcnow():
    """返回当前 UTC 时间。"""
    return datetime.now(UTC)
