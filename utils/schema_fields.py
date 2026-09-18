from datetime import UTC, datetime

from marshmallow import fields


class UTCDateTime(fields.DateTime):
    """对外统一：带 +00:00 的 ISO8601 UTC 字符串。"""

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)   # 库内为 naive UTC
        else:
            value = value.astimezone(UTC)
        return value.isoformat()                # 2026-09-11T07:30:00+00:00
