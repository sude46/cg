# exceptions/database_error.py
from .base import BaseError

class DatabaseError(BaseError):
    """数据库操作异常（如约束冲突、连接失败、事务提交失败）"""
    code = 50001
    http_status = 500
    message = "数据库操作失败"

__all__ = ["DatabaseError"]