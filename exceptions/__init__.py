# exceptions/__init__.py
"""
顶级异常目录入口：外部代码只需从这里导入，无需关心内部模块拆分
"""
# 从子模块导入所有异常类
from .base import BaseError
from .validation_error import ValidationError
from .resource_error import ResourceNotFoundError
from .auth_error import AuthenticationError, PermissionError
from .database_error import DatabaseError
from .rate_limit_error import RateLimitError
from .conflict_error import ConflictError

# 明确对外暴露的异常类（核心：外部只能导入这些）
__all__ = [
    "BaseError",
    "ValidationError",
    "ResourceNotFoundError",
    "AuthenticationError",
    "PermissionError",
    "DatabaseError",
    "RateLimitError",
    "ConflictError"
]