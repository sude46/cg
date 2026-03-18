# exceptions/validation_error.py
from .base import BaseError

class ValidationError(BaseError):
    """参数校验失败异常（修复：统一命名，继承 BaseError）"""
    code = 40000          # 唯一异常码（400=HTTP状态码，00=细分）
    http_status = 400
    message = "参数验证失败"

# 明确导出的类（避免导出内部变量）
__all__ = ["ValidationError"]