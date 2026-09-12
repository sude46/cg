import os
from datetime import timedelta

from dotenv import load_dotenv

from .base import BaseConfig

load_dotenv()

class TestingConfig(BaseConfig):
    """测试环境配置"""
    TESTING = True
    DEBUG = False
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 测试环境使用内存数据库
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_BINDS = {}
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {
            "check_same_thread": False
        }
    }

    # 强制关闭数据库连接服用，避免跨测试用力的数据污染
    SQLALCHEMY_POOL_RECYCLE = 1
    SQLALCHEMY_POOL_SIZE = 1

    # 测试环境安全配置
    WTF_CSRF_ENABLED = False

    # 测试环境安全配置
    SECRET_KEY = os.getenv("SECRET_KEY", "test_secret_key_123456")
    # 测试用固定 Fernet key（仅用于加密/解密 MFA secret 的单元测试）
    MFA_ENCRYPTION_KEY = "Hn5Kx-D3nfeBKB8XZSC0S-VJoo6FhzLChdzN-jN6xPw="

    # 缩短JWT过期时间（从默认的15分钟改为1分钟），提升测试认证流程效率
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=1)
    # 测试环境邮件配置(使用内存队列)
    MAIL_SUPPRESS_SEND = True

    BCRYPT_LOG_ROUNDS = 4  # 测试环境降低轮次，减少测试耗时

    #日志配置
    LOG_LEVEL="DEBUG"
    LOG_FORMAT="%(asctime)s%(levelname)s%(request_id)s%(message)s"
    INFO_LOG_FILE=""
    ERROR_LOG_FILE=""


    RATE_LIMIT_STORAGE = "memory://"  # 内存存储，无需Redis
    RATE_LIMIT_DEFAULT = []  # 清空默认限流规则

    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache"



    @classmethod
    def init_app(cls, app):
        """测试环境特定初始化"""
        super().init_app(app)
        # 禁用异常时的上下文保留，避免内存泄露和数据残留
        app.config['PRESERVE_CONTEXT_ON_EXCEPTION'] = False

