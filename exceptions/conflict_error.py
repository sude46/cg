# exceptions/conflict_error.py
from .base import BaseError

class ConflictError(BaseError):
    """资源冲突异常（如创建已存在的用户名/邮箱）"""
    code = 40900
    http_status = 409
    message = "资源冲突，操作无法完成"

__all__ = ["ConflictError"]