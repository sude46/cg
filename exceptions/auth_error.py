# exceptions/auth_error.py
from .base import BaseError

class AuthenticationError(BaseError):
    """认证失败异常（如Token过期/无效）"""
    code = 40100
    http_status = 401
    message = "认证失败，请先登录或刷新Token"

class PermissionError(BaseError):
    """权限不足异常（如普通用户操作管理员接口）"""
    code = 40300
    http_status = 403
    message = "权限不足，无法执行该操作"

__all__ = ["AuthenticationError", "PermissionError"]