# exceptions/base.py
import logging
from typing import Dict, Any

# 初始化日志
logger = logging.getLogger(__name__)

class BaseError(BaseException):
    """
    所有业务异常的基类（修复：继承 BaseException 而非 Exception）
    解决：全局异常处理器可统一捕获所有业务异常
    """
    # 统一异常码规则：前3位=HTTP状态码，后2位=业务细分（唯一不重复）
    code: int = 50000        # 全局唯一异常码（修复：避免复用）
    http_status: int = 500   # 对应HTTP状态码
    message: str = "服务器内部错误"  # 默认提示

    def __init__(self, message: str = None, extra: Dict[str, Any] = None):
        # 支持自定义异常消息
        self.message = message or self.message
        # 扩展字段（如失败的参数名、用户ID等，供前端精细化处理）
        self.extra = extra or {}
        super().__init__(self.message)
        # 自动打印异常日志（便于排查问题）
        self._log_exception()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为前端可用的JSON格式（标准化返回）"""
        return {
            "code": self.code,
            "message": self.message,
            "http_status": self.http_status,
            "extra": self.extra
        }

    def _log_exception(self) -> None:
        """打印异常日志（包含上下文，修复：无日志的问题）"""
        logger.error(
            f"业务异常 | 异常码：{self.code} | 消息：{self.message} | 扩展信息：{self.extra}"
        )

    def __str__(self) -> str:
        return f"[{self.code}] {self.message} (详情：{self.extra})"