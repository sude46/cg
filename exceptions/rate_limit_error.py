# exceptions/rate_limit_error.py
from .base import BaseError

class RateLimitError(BaseError):
    """接口限流异常（修复：统一命名为 RateLimitError，废弃 LimitError）"""
    code = 42900
    http_status = 429
    message = "请求过于频繁，请稍后再试"

# 仅导出规范命名的类，废弃 LimitError
__all__ = ["RateLimitError"]