from flask import Flask, g, request
import logging
import os
import time
from config import get_config
from core.database import db, migrate
from core.extensions import bcrypt, jwt, mail
from flask_jwt_extended import get_jwt_identity
from flask_wtf.csrf import CSRFProtect

from core.logging_config import init_structured_logger
from core.blueprint_registry import register_all_blueprints
from app.common.error_handlers import register_error_handlers

from middlewares.request_hooks import register_request_hook

# 导入所有模型，确保 db.create_all() 创建完整表结构
from app.users.models import User
from app.posts.models import Post
from app.comments.models import Comment
from app.likes.models import Like
from app.follows.models import Follow
from app.notifications.models import Notification
# 如果有其他模型，继续导入

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

    # 初始化中间件
    from middlewares.logging_middleware import init_logging_middleware
    from middlewares.error_middleware import init_error_handlers
    from middlewares.auth_middleware import init_auth_middleware
    from middlewares.rate_limit_middleware import init_rate_limit_middleware
    from middlewares.cors_middleware import init_cors
    from middlewares.security_mw import init_security_headers

    init_logging_middleware(app)
    init_error_handlers(app)
    init_auth_middleware(app)
    init_rate_limit_middleware(app)
    init_cors(app)
    init_security_headers(app)

    # 注册全局异常处理器
    register_error_handlers(app)
    register_request_hook(app)

    # 开发环境自动建表
    with app.app_context():
        if is_dev:
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

    return app





