"""
限流中间件 - 符合工厂模式设计
通过 app 实例挂载，避免全局状态
"""
from functools import wraps
from flask import current_app, request, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded
import logging

logger = logging.getLogger(__name__)


def init_rate_limit_middleware(app):
    """
    初始化限流中间件 - 工厂模式
    在 create_app 中调用，符合依赖注入原则
    """
    if app.config.get("TESTING"):
        # 测试环境：挂载空实现，不实际限流
        app.limiter = None
        app.route_limit = _empty_route_limit
        return
    
    # 生产环境：初始化 Flask-Limiter
    storage_uri=app.config.get('RATE_LIMIT_STORAGE','memory://')
    if storage_uri=='memory://':
        logger.warning("使用内存存储限流数据，适合开发环境，不推荐生产环境")
    limiter = Limiter(
        app=app,
        key_func=_get_identifier,
        default_limits=app.config.get('RATE_LIMIT_DEFAULT', ['100 per minute']),
        storage_uri=storage_uri,
        strategy="fixed-window"
    )
    
    # 挂载到 app 实例
    app.limiter = limiter
    
    # 提供路由限流装饰器)
    app.route_limit = _make_route_limit(limiter)
    
    # 注册错误处理器
    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(e):
        retry_after = getattr(e, 'retry_after', 60)
        return {
            "code": 429,
            "error": "请求过于频繁，请稍后重试",
            "retry_after": retry_after
        }, 429
    
    logger.info(f"Rate limiter initialized with storage: {storage_uri}")


def _get_identifier():
    """获取限流标识：优先用户ID，其次IP"""
    try:
        from flask_jwt_extended import get_jwt_identity
        user_id = get_jwt_identity()
        if user_id:
            return f"user:{user_id}"
    except:
        pass
    return get_remote_address()


def _make_route_limit(limiter):
    """
    创建路由限流装饰器工厂
    提前绑定 limiter，避免每次请求动态创建函数对象
    """
    def decorator(limit_value):
        limmit_decorator = limiter.limit(limit_value)
        def wrapper(f):
                return limmit_decorator(f)
        return wrapper
    return decorator


def _empty_route_limit(limit_value):
    """测试环境空实现"""
    def decorator(f):
        return f
    return decorator


# 辅助函数：在应用上下文中安全获取限流器
def get_route_limit():
    """
    延迟获取 route_limit
    在应用上下文可用时调用
    """
    from flask import current_app
    return getattr(current_app, 'route_limit', _empty_route_limit)
