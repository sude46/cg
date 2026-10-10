"""flask-restx 错误响应桥接。

flask-restx 会拦截它自己端点的 404/405（``Api._should_use_fr_error_handler``），
返回 ``{"message": ...}``，绕过 Flask 的 ``@app.errorhandler``，与项目统一契约
``{code, message, request_id}`` 不一致。

这里给 ``Api.handle_error`` 包一层：对它处理的 ``HTTPException`` 改用统一格式，
并保留原 HTTP 状态码与 ``Allow`` / ``WWW-Authenticate`` 等响应头。
只在进程内安装一次，未改动任何 ``app/*/routes.py``。
"""
import json
import logging

from flask import current_app, g, request
from flask_restx.api import Api
from werkzeug.exceptions import HTTPException

from app.common.exceptions import BaseError

logger = logging.getLogger(__name__)

# HTTP 状态码 -> 业务错误码（与 app/common/exceptions.py 的 error_code 对齐）
HTTP_TO_BUSINESS_CODE = {
    400: 10001,  # ValidationError
    401: 10004,  # AuthenticationError
    403: 10003,  # PermissionError
    404: 10002,  # ResourceNotFoundError
    405: 10009,  # MethodNotAllowed
    409: 10007,  # ConflictError
    429: 10006,  # RateLimitError
    500: 5000,   # INTERNAL_ERROR
}


def business_code_for_status(status: int) -> int:
    return HTTP_TO_BUSINESS_CODE.get(status, status)


def format_http_exception(e: HTTPException):
    """把 HTTPException 转成统一契约的 JSON 响应（保留原状态码/响应头）。"""
    status = e.code or 500
    response = e.get_response()  # 保留 Allow / WWW-Authenticate 等头
    body = {
        "code": business_code_for_status(status),
        "message": e.description,
        "request_id": g.get("request_id", "N/A"),
    }
    if status == 405:
        allowed = getattr(e, "valid_methods", None)
        if allowed:
            body["details"] = {"allowed_methods": sorted(allowed)}
    response.set_data(json.dumps(body, ensure_ascii=False))
    response.content_type = "application/json"
    return response


_installed = False


def install_restx_error_bridge():
    """包装 flask-restx 的 handle_error（幂等，进程内只装一次）。"""
    global _installed
    if _installed:
        return
    original = Api.handle_error

    def handle_error(self, e):
        handlers = getattr(self, "_own_and_child_error_handlers", {})

        # 自定义业务异常（BaseError 及其子类）：flask-restx 的 handle_error 不会
        # 走 Flask @app.errorhandler。生产环境 PROPAGATE_EXCEPTIONS=False 时，
        # restx 会把 AuthenticationError 等直接吞成通用 500（而非 401），
        # 导致前端拿不到正确状态码。这里显式转交给 Flask 注册的处理器，
        # 保持统一 {code, message, request_id} 契约。
        if isinstance(e, BaseError) and not any(
            isinstance(e, exc_type) for exc_type in handlers
        ):
            try:
                handler = current_app._find_error_handler(e, request.blueprints)
                if handler is not None:
                    return current_app.ensure_sync(handler)(e)
            except Exception as inner:  # 桥接失败则回退 restx 默认处理
                logger.error(f'restx 业务异常桥接失败，回退默认处理: {inner}')

        if isinstance(e, HTTPException) and not any(
            isinstance(e, exc_type) for exc_type in handlers
        ):
            try:
                return format_http_exception(e)
            except Exception as inner:  # 桥接失败则回退 restx 默认处理
                logger.error(f'restx 错误桥接失败，回退默认处理: {inner}')
        return original(self, e)

    Api.handle_error = handle_error
    _installed = True
    logger.info('flask-restx 错误响应桥接已安装')
