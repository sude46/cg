from flask import request, g
import time
import logging
import uuid
import json
from datetime import datetime, timezone
from typing import Dict, Any
import sys
import traceback

logger = logging.getLogger(__name__)  # 新增：独立logger


def init_logging_middleware(app):
    """初始化结构化日志中间件：request_id + 请求/响应日志 + 敏感信息过滤"""

    def filter_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤敏感信息（密码、token等）"""
        sensitive_keys = ['password', 'token', 'secret', 'authorization']
        return {
            k: '***' if k.lower() in sensitive_keys else v
            for k, v in data.items()
        }

    @app.before_request
    def before_request():
        """请求前：生成request_id，记录开始时间，日志脱敏"""
        # 防止覆盖已有值（如反向代理传递的X-Request-ID）
        g.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        g.start_time = time.time()

        # 构造请求日志（脱敏）
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": "INFO",
            "request_id": g.request_id,
            "method": request.method,
            "path": request.path,
            "remote_addr": request.headers.get('X-Forwarded-For', request.remote_addr) or "unknown",
            "user_agent": str(request.user_agent) if request.user_agent else None,
            "content_length": request.content_length or 0
        }

        # 可选：记录请求体（仅非文件、非敏感）
        if request.method in ['POST', 'PUT', 'PATCH'] and not request.is_json:
            try:
                log_data['request_body'] = filter_sensitive_data(request.get_json(silent=True) or {})
            except Exception:
                log_data['request_body'] = 'non-json body'

        logger.info(json.dumps(log_data, ensure_ascii=False))

    @app.after_request
    def after_request(response):
        """请求后：记录响应日志，设置响应头"""
        if not hasattr(g, 'start_time'):
            logger.warning(f"Request {g.request_id if hasattr(g, 'request_id') else 'unknown'} missing start time")
            return response

        duration = time.time() - g.start_time
        # 设置响应头
        response.headers['X-Response-Time'] = f'{duration:.3f}s'
        response.headers['X-Request-ID'] = g.request_id

        # 响应日志
        log_level = logging.INFO if response.status_code < 400 else logging.WARNING
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": "INFO" if log_level == logging.INFO else "WARNING",
            "request_id": g.request_id,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "path": request.path,
            "response_length": response.content_length or 0
        }

        logger.log(log_level, json.dumps(log_data, ensure_ascii=False))
        return response

    # 新增：请求异常日志（补充before_request未覆盖的场景）
    @app.teardown_request
    def teardown_request(exception=None):
        if exception is not None:
            exc_info = sys.exc_info()
            formatted_traceback = ''.join(traceback.format_exception(*exc_info))
            app.logger.error(f"Unhandled exception: {formatted_traceback}")