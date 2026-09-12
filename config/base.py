import os
import secrets
import warnings
from datetime import timedelta

# 加载环境变量
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


class BaseConfig:
    """
    基础配置类
    原则：只包含 Flask 和基础设施配置，不包含业务规则
    """

    # ==================== Flask 核心配置 ====================
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        warnings.warn("SECRET_KEY未配置，使用随机值（仅开发环境）", UserWarning)
        SECRET_KEY = 'dev-key-' + secrets.token_hex(32)

    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    if not JWT_SECRET_KEY:
        warnings.warn("JWT_SECRET_KEY未配置", UserWarning)
        JWT_SECRET_KEY = 'jwt-dev-' + secrets.token_hex(32)

    DEBUG = False
    TESTING = False

    # ==================== 数据库配置 ====================
    #主库（写操作）：读取DEV_DATABASE_URL
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL') or 'sqlite:///app.db'
    #从库
    SQLALCHEMY_BINDS={
        'replica': os.getenv('REPLICA_DATABASE_URL') or SQLALCHEMY_DATABASE_URI
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'isolation_level':'READ COMMITTED',
    }
    # 从库连接池单独配置
    SQLALCHEMY_ENGINE_OPTIONS_REPLICA = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'isolation_level':'READ COMMITTED',
    }

    # ==================== JWT 配置（基础设施）====================
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ['access', 'refresh']
    # 使用整数 user_id 作为 JWT subject，禁用 PyJWT 对 sub 必须是字符串的校验
    JWT_VERIFY_SUB = False

    # ==================== Redis 配置 ====================
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
    REDIS_URL = os.getenv('REDIS_URL') or f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'

    # 哨兵配置
    REDIS_SENTINEL_HOST = os.getenv("REDIS_SENTINEL_HOST", "")
    REDIS_SENTINEL_MASTER_NAME = os.getenv("REDIS_SENTINEL_MASTER_NAME", "mymaster")

    MFA_ENCRYPTION_KEY = os.getenv('MFA_ENCRYPTION_KEY', '')

    REDIS_SOCKET_TIMEOUT=2
    REDIS_SOCKET_CONNECT_TIMEOUT=2
    REDIS_DECODE_RESPONSES=True
    REDIS_POOL_SIZE=10

    # Celery 配置（与业务缓存分库，避免 key 冲突）
    #   DB 0: 业务缓存（RedisCache）
    #   DB 1: Celery result backend
    #   DB 2: Celery broker（消息队列）
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL') or f'redis://{REDIS_HOST}:{REDIS_PORT}/2'
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND') or f'redis://{REDIS_HOST}:{REDIS_PORT}/1'


    #=====================Elasticsearch配置=====================
    ELASTICSEARCH_ENABLED=os.getenv('ELASTICSEARCH_ENABLED','true').lower()=='true'
    ELASTICSEARCH_HOST=os.getenv('ELASTICSEARCH_HOSTS','http://localhost:9200')
    ELASTICSEARCH_TIMEOUT=int(os.getenv('ELASTICSEARCH_TIMEOUT','30'))

    @property
    def ES_HOST_LIST(self):
        '''将ES_HOST解析为列表'''
        if isinstance(self.ELASTICSEARCH_HOST,list):
            return self.ELASTICSEARCH_HOST
        return [h.strip() for h in self.ELASTICSEARCH_HOST.split(",") if h.strip()]


    # ==================== 邮件配置 ====================
    MAIL_SERVER = os.getenv('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.getenv('MAIL_PORT') or 587)
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')

    # ==================== 文件上传配置 ====================
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB（Flask 限制）

    @property
    def UPLOAD_FOLDER(self):
        return os.path.join(PROJECT_ROOT, 'app', 'static', 'uploads')

    # ==================== 安全配置（基础设施）====================
    BCRYPT_LOG_ROUNDS = int(os.getenv('BCRYPT_LOG_ROUNDS', 12))
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # ==================== CORS 配置 ====================
    CORS_RESOURCES = os.getenv("CORS_RESOURCES", r"/*")
    CORS_SUPPORTS_CREDENTIALS = True
    CORS_ALLOWED_ORIGINS=[
            o.strip() for o in os.getenv(
                'CORE_ALLOWED_ORIGINS',
                'http://localhost:5173'
                ).split(',') if o.strip()
            ]

    # ==================== 日志配置 ====================
    LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    @classmethod
    def init_app(cls, app):
        """初始化应用配置"""
        # 创建上传目录
        os.makedirs(cls().UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)


