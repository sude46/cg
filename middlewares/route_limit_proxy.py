"""
限流装饰器代理 - 符合依赖注入原则
在装饰器执行时才获取真实的 limiter，避免模块导入时的循环依赖
"""
from functools import wraps
from flask import current_app


class RouteLimitProxy:
    """
    限流装饰器代理类
    延迟从 current_app 获取真实的 route_limit
    符合工厂模式和依赖注入原则
    """
    
    def __call__(self, limit_value):
        """
        返回一个装饰器，在运行时从 app 获取真正的限流器
        """
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                # 在请求上下文中获取真实的 route_limit
                route_limit = getattr(current_app, 'route_limit', None)
                
                if route_limit is None:
                    # 限流器未初始化，直接执行
                    return f(*args, **kwargs)
                
                # 使用真实的限流器
                limited_f = route_limit(limit_value)(f)
                return limited_f(*args, **kwargs)
            
            return wrapper
        return decorator


# 全局代理实例（单例，但延迟绑定真实实现）
route_limit = RouteLimitProxy()
