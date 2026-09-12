import json
import logging
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime
from typing import Any

from flask import g, request

logger = logging.getLogger(__name__)


def init_logging_middleware(app):
    """初始化结构化日志中间件：request_id + 请求/响应日志 + 敏感信息过滤"""

    def filter_sensitive_data(data: dict[str, Any],depth:int=0) -> dict[str, Any]:
        """过滤敏感信息（密码、token等）"""
        if depth>3:
            return '[nested]'
        if not isinstance(data,dict):
            return data
        sensitive_keys = {
            'password', 'token', 'secret', 'authorization',
            'cookie', 'session', 'api_key', 'apikey', 'access_token',
            'refresh_token', 'jwt'
        }
        filtered={}
        for k,v in data.items():
            key_lower=k.lower()
            if key_lower in sensitive_keys:
                filtered[k]='***'
            elif isinstance(v,dict):
                filtered[k]=filter_sensitive_data(v,depth+1)
            elif isinstance(v,list) and depth<2:
                filtered[k]=[filter_sensitive_data(item,depth+1) if isinstance(item,dict) else item for item in v[:10]]
            else:
                filtered[k]=v
        return filtered

    @app.before_request
    def before_request():
        """请求前：生成request_id，记录开始时间，日志脱敏"""
        # 防止覆盖已有值（如反向代理传递的X-Request-ID）
        g.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        g.start_time = time.time()

        # 构造请求日志（脱敏）
        log_data = {
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "level": "INFO",
            "request_id": g.request_id,
            "method": request.method,
            "path": request.path,
            "remote_addr": request.headers.get('X-Forwarded-For', request.remote_addr) or "unknown",
            "user_agent": str(request.user_agent) if request.user_agent else None,
            "content_length": request.content_length or 0
        }


        # 安全记录请求体，避免阻塞和内存溢出
        if request.method in ['POST', 'PUT', 'PATCH'] and request.is_json:
            try:
                #限制请求体大小（防止json阻塞）
                if request.content_length and request.content_length<10*1024:
                    body=request.get_json(silent=True) or {}
                    log_data['request_body']=filter_sensitive_data(body)
                else:
                    log_data['request_body']='[too large]'
            except Exception:
                log_data['request_body'] = 'parse error'

        #异步日志或异常捕获，防止主线程阻塞
        try:
            logger.info(json.dumps(log_data, ensure_ascii=False, default=str))
        except (TypeError,ValueError) as e:
            # 序列化失败时降级为字符串
            logger.info(f"Request log serialization failed: {e}, data: {str(log_data)}")


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
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "level": "INFO" if log_level == logging.INFO else "WARNING",
            "request_id": g.request_id,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "path": request.path,
            "response_length": response.content_length or 0
        }
        try:
            logger.log(log_level,json.dumps(log_data,ensure_ascii=False,default=str))
        except Exception as e:
            logger.error(f'Failed to log response: {e}, data: {str(log_data)}')
        return response

    # 新增：请求异常日志（补充before_request未覆盖的场景）
    @app.teardown_request
    def teardown_request(exception=None):
        if exception is not None:
            exc_info = sys.exc_info()
            formatted_traceback = ''.join(traceback.format_exception(*exc_info))
            app.logger.error(f"Unhandled exception: {formatted_traceback}")
