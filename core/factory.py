
from flask import Flask

from app.common.error_handlers import register_error_handlers
from app.common.events import event_bus
from app.feeds.handlers import register_feed_handlers

# 如果有其他模型，继续导入
# 导入通知模块的事件订阅注册函数
from app.notifications.services import register_notification_event_handlers

# 导入所有模型，确保 db.create_all() 创建完整表结构
from config import get_config
from core.blueprint_registry import register_all_blueprints
from core.celery_app import (
    celery_app as _celery_app,  # noqa: F401  确保 shared_task 绑定到项目 Celery 实例
)
from core.database import db, migrate
from core.db_router import db_router
from core.extensions import bcrypt, jwt, mail
from core.logging_config import init_structured_logger
from core.restx_error_bridge import install_restx_error_bridge
from services.search.event_handlers import register_search_event_handlers


def create_app(config_name: str = None) -> Flask:
    app = Flask(__name__)

    # 获取配置类
    config_class = get_config(config_name)

    # 实例化配置类，使 property 被调用
    config_instance = config_class()

    # 从实例加载配置
    app.config.from_object(config_instance)

    if hasattr(config_class, "init_app"):
        config_class.init_app(app)

    is_dev = app.config.get("DEBUG", False) or app.config.get("FLASK_ENV") == "development"
    is_test = app.config.get("TESTING", False)
    app.logger.info(f"[ENV] development={is_dev},testing={is_test}")

    # 初始化日志
    init_structured_logger(app)

    # 测试环境关闭 CSRF
#    if not is_test:
 #       CSRFProtect(app)

    db.init_app(app)
    migrate.init_app(app, db)
    db_router.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)

    # 初始化 RedisClient
    try:
        from utils.redis_util import RedisClient
        RedisClient.init_app(app)
        app.logger.debug('RedisClient 初始化成功')
    except (ImportError, AttributeError) as e:
        app.logger.warning(f'RedisClient初始化失败:{str(e)}')

    # 初始化 Elasticsearch
    if app.config.get('ELASTICSEARCH_ENABLED', True):
        from core.es_client import es_client  # ✅ 从 core 导入
        from services.search.config import SearchConfig  # ✅ 业务配置
        from services.search.document import PostDocument

        # 初始化业务配置
        SearchConfig.init_app(app.config)

        # 连接 ES（传入配置）
        if es_client.connect(app.config):
            PostDocument.create_index()
            app.logger.info("Elasticsearch 初始化完成")
        else:
            app.logger.warning("Elasticsearch 连接失败，搜索功能将降级到数据库")
    else:
        app.logger.info("Elasticsearch 已禁用")


    # 初始化中间件
    from middlewares.auth_middleware import init_auth_middleware
    from middlewares.cors_middleware import init_cors
    from middlewares.logging_middleware import init_logging_middleware
    from middlewares.metrics_middleware import init_metrics_middleware
    from middlewares.rate_limit_middleware import init_rate_limit_middleware
    from middlewares.security_mw import init_security_headers

    init_metrics_middleware(app)
    init_logging_middleware(app)
    init_auth_middleware(app)
    init_rate_limit_middleware(app)
    init_cors(app)
    init_security_headers(app)

    # 注册全局异常处理器
    register_error_handlers(app)
    # 让 flask-restx 端点（404/405 等）也返回统一错误格式
    install_restx_error_bridge()

    # 开发环境自动建表
    with app.app_context():
        if is_dev and app.config.get('AUTO_CREATE_TABLES', True):
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            # 检查核心表是否存在，不存在才创建
            if not inspector.has_table("users"):
                db.create_all()  # 现在所有已导入的模型都会被创建
                app.logger.warning("[DEV MODE] Auto-creating database tables (only for development)")
        elif is_test:
            db.create_all()
            app.logger.info("[TEST MODE] Database tables created in memory")
        else:
            app.logger.info("[PROD MODE] Database tables must be created via migrate")

    # 注册蓝图
    register_all_blueprints(app)

    # 注册事件订阅器
    register_notification_event_handlers()
    register_search_event_handlers()
    register_feed_handlers()
    event_bus.start(app)

    return app





