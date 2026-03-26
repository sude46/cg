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
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
    }
    
    # ==================== JWT 配置（基础设施）====================
    # 注意：这是 Flask-JWT-Extended 的配置，不是业务规则
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ['access', 'refresh']
    
    # ==================== Redis 配置 ====================
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
    REDIS_URL = os.getenv('REDIS_URL') or f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'
    
    # Celery 使用相同的 Redis
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL') or REDIS_URL
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND') or f'{REDIS_URL}/1'
    
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
    
    # ==================== 日志配置 ====================
    LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def init_app(cls, app):
        """初始化应用配置"""
        # 创建上传目录
        os.makedirs(cls().UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)


class DevelopmentConfig(BaseConfig):
    """开发环境配置"""
    DEBUG = True
    SQLALCHEMY_ECHO = True
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)  # 开发时方便测试


class TestingConfig(BaseConfig):
    """测试环境配置"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(BaseConfig):
    """生产环境配置"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # HTTPS only
    BCRYPT_LOG_ROUNDS = 14  # 更强的加密


# 配置映射
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(env=None):
    """获取配置类"""
    env = env or os.getenv('FLASK_ENV', 'development')
    return config.get(env, DevelopmentConfig)

