# 统一函数式中间件导出
# 注意：route_limit 从独立模块导入，避免循环依赖

# 先导出独立的代理（不依赖其他中间件）
from .route_limit_proxy import route_limit  # noqa: I001

# 再导出初始化函数
from .auth_middleware import init_auth_middleware
from .cors_middleware import init_cors
from .logging_middleware import init_logging_middleware
from .metrics_middleware import init_metrics_middleware
from .rate_limit_middleware import init_rate_limit_middleware
from .security_mw import init_security_headers

__all__ = [
    'route_limit',  # 延迟代理，最先导出
    'init_auth_middleware',
    'init_logging_middleware',
    'init_cors',
    'init_rate_limit_middleware',
    'init_security_headers',
    'init_metrics_middleware',
    ]


def init_all_middlewares(app):
    """
    批量初始化所有中间件（按依赖顺序）

    顺序逻辑：
    Metrics 最先（计时最准），然后 CORS、安全头、日志、限流、认证
    1. CORS 最先（处理 OPTIONS 预检，但预检在 auth 中已兼容）
    2. 安全头（所有响应都需要）
    3. 日志（记录所有请求）
    4. 限流（在认证前拦截暴力请求）
    5. 认证最后（依赖前面的中间件设置的环境）
    """
    init_metrics_middleware(app)
    init_cors(app)
    init_security_headers(app)
    init_logging_middleware(app)
    init_rate_limit_middleware(app)
    init_auth_middleware(app)
