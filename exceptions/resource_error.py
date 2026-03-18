# exceptions/resource_error.py
from .base import BaseError

class ResourceNotFoundError(BaseError):
    """资源不存在异常（如查询的用户/帖子/订单不存在）"""
    code = 40400
    http_status = 404
    message = "请求的资源不存在"

__all__ = ["ResourceNotFoundError"]