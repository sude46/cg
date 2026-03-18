# 统一函数式中间件导出
# 初始化顺序建议：cors → security → logging → rate_limit → auth → error
from .auth_middleware import init_auth_middleware
from .logging_middleware import init_logging_middleware
from .error_middleware import init_error_handlers
from .cors_middleware import init_cors
from .rate_limit_middleware import init_rate_limit_middleware
from .security_mw import init_security_headers

__all__ = [
    'init_auth_middleware',
    'init_logging_middleware',
    'init_error_handlers',
    'init_cors',
    'init_rate_limit_middleware',
    'init_security_headers',
]

# 新增：批量初始化中间件（简化顶层调用）
def init_all_middlewares(app):
    """批量初始化所有中间件（按依赖顺序）"""
    init_cors(app)
    init_security_headers(app)
    init_logging_middleware(app)
    init_rate_limit_middleware(app)
    init_auth_middleware(app)
    init_error_handlers(app)

__all__.append('init_all_middlewares')