from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded
from flask import request, g
from app.common.exceptions import RateLimitError
import logging
import re

logger = logging.getLogger(__name__)


def get_identifier() -> str:
    """优化：优先用户ID，其次真实IP（支持反向代理）"""
    # 已认证用户：用user_id限流（更精准）
    if hasattr(g, 'current_user') and g.current_user:
        return f"user:{g.current_user.id}"
    # 未认证用户：获取真实IP（兼容Nginx反向代理）
    return request.headers.get('X-Forwarded-For', get_remote_address()).split(',')[0].strip()


def init_rate_limit_middleware(app):
    """初始化限流中间件：Redis存储 + IP/用户级限流 + 精准retry_after解析"""

    if app.config.get("TESTING"):
        app.limiter=None
        #测试环境也挂载空的route_limit,避免路由调用时报错
        def empty_route_limit(limit:str):
            def decorator(f):
                return f
            return decorator
        app.route_limit=empty_route_limit
        return 

    # 生产环境必须用Redis存储（替换memory）
    storage_uri = app.config.get('RATE_LIMIT_STORAGE', 'redis://localhost:6379/0')
    # 从配置读取限流策略
    default_limits = app.config.get('RATE_LIMIT_DEFAULT', ['100 per minute'])

    limiter = Limiter(
        app=app,
        key_func=get_identifier,  # 支持IP/用户级限流
        default_limits=default_limits,
        storage_uri=storage_uri,
        storage_options=app.config.get('RATE_LIMIT_STORAGE_OPTIONS', {}),
        strategy="fixed-window"  # 明确限流策略（可选：moving-window）
    )

    app.limiter = limiter

    # 注册全局错误处理器，兼容 Flask-Limiter 3.x
    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_exceeded(e):
        logger.warning(f'Rate limit exceeded: {e.description} ID: {get_identifier()}')
        retry_after_match = re.search(r'retry after (\d+)', e.description, re.IGNORECASE)
        retry_after = retry_after_match.group(1) if retry_after_match else None
        return {
            "code": 429,
            "error": "请求过于频繁，请稍后重试",
            "details": {"retry_after": int(retry_after) if retry_after else 60}
        }, 429
    #自定义路由限流装饰器
    def route_limit(limit: str):
        def decorator(f):
            return limiter.limit(limit)(f)
        return decorator

    app.route_limit = route_limit  # 挂载到app，供路由使用
