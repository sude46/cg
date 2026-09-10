from flask import jsonify, request, current_app, g
import logging
import traceback
from datetime import datetime
from typing import Dict, Any

from app.common.exceptions import (
    BaseError, 
    ValidationError, 
    ResourceNotFoundError, 
    PermissionError, 
    AuthenticationError,
    RateLimitError,  # 新增：导入限流异常
    DatabaseError
)

logger = logging.getLogger(__name__)


def init_error_handlers(app):
    """注册全局错误处理：精准异常匹配 + 完整request_id + 调试信息"""

    @app.errorhandler(BaseError)
    def handle_app_exception(error: BaseError):
        return _format_error_response(error)

    # 优先处理自定义RateLimitError（避免被429覆盖）
    @app.errorhandler(RateLimitError)
    def handle_rate_limit_error(error: RateLimitError):
        return _format_error_response(error)

    @app.errorhandler(400)
    def handle_bad_request(error):
        return _format_error_response(ValidationError("请求参数错误", error_code=10001))

    @app.errorhandler(401)
    def handle_unauthorized(error):
        return _format_error_response(AuthenticationError("未授权访问", error_code=10002))

    @app.errorhandler(403)
    def handle_forbidden(error):
        return _format_error_response(PermissionError("权限不足", error_code=10003))

    @app.errorhandler(404)
    def handle_not_found(error):
        return _format_error_response(ResourceNotFoundError("资源未找到", error_code=10004))

    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        return _format_error_response(BaseError("请求方法不允许", status_code=405, error_code=10007))

    # 429仅作为兜底（优先用自定义RateLimitError）
    @app.errorhandler(429)
    def handle_rate_limit_fallback(error):
        return _format_error_response(RateLimitError("请求过于频繁", error_code=10006))

    @app.errorhandler(500)
    def handle_internal_server_error(error):
        tb = traceback.format_exc()
        logger.error(f"Internal Server Error: {tb}")
        return _format_error_response(BaseError("服务器内部错误", status_code=500, error_code=10000))

    # 新增：数据库异常处理
    @app.errorhandler(DatabaseError)
    def handle_database_error(error):
        return _format_error_response(BaseError("数据库操作失败", status_code=500, error_code=10008))


def _format_error_response(error: BaseError) -> tuple:
    """标准错误响应格式：补全request_id，优化debug信息"""
    # 优先从g获取request_id（logging_middleware生成），其次从请求头
    request_id = getattr(g, 'request_id', request.headers.get("X-Request-ID")) or "unknown"

    response: Dict[str, Any] = {
        "code": error.error_code,
        "error": error.message,
        "details": error.details or {},
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "path": request.path,
    }

    # Debug模式：暴露详细信息（仅开发环境）
    if current_app.config.get("DEBUG"):
        response["debug"] = {
            "exception_type": error.__class__.__name__,
            "traceback": traceback.format_exc(),
            "request_method": request.method,
            "request_headers": dict(request.headers)
        }

    return jsonify(response), error.status_code