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

    # 开发环境是否自动建表（运行 alembic 迁移时需显式设 AUTO_CREATE_TABLES=false）
    AUTO_CREATE_TABLES = os.getenv('AUTO_CREATE_TABLES', 'true').lower() == 'true'

    # 是否启动 Redis 事件总线消费者。只有 web 进程需要：每个 gunicorn worker 一个消费
    # 线程，多进程共享 queue/processing，at-least-once + reaper 回收 -> 多消费者安全。
    # celery worker/beat 设 false，避免与 web 重复消费同一队列。
    EVENT_BUS_ENABLED = os.getenv('EVENT_BUS_ENABLED', 'true').lower() == 'true'

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

    # ==================== 限流配置 ====================
    # 存储后端：生产务必用 Redis，多 worker/多实例共享计数；内存仅适合开发
    RATE_LIMIT_STORAGE = os.getenv('RATE_LIMIT_STORAGE') or 'memory://'
    # 默认限流规则，支持逗号分隔多条，如 "100 per minute,1000 per hour"
    RATE_LIMIT_DEFAULT = [
        s.strip() for s in os.getenv('RATE_LIMIT_DEFAULT', '100 per minute').split(',')
        if s.strip()
    ]

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

    # 存储后端：local（本地磁盘）；后续可扩展 s3/minio
    STORAGE_BACKEND = os.getenv('STORAGE_BACKEND', 'local')
    # 图片回显基址（local 默认 /uploads/files；生产可指向 CDN/OSS）
    STORAGE_PUBLIC_BASE = os.getenv('STORAGE_PUBLIC_BASE', 'http://localhost:5000/uploads/files')
    # 单图大小上限（默认 5MB）
    UPLOAD_MAX_BYTES = int(os.getenv('UPLOAD_MAX_BYTES', str(5 * 1024 * 1024)))
    # 允许的图片 MIME（禁止 svg）
    UPLOAD_ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}

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
                'CORS_ALLOWED_ORIGINS',
                'http://localhost:5173'
                ).split(',') if o.strip()
            ]

    # ==================== 搜索降级（熔断） ====================
    # 降级模式：fallback=带护栏的 DB LIKE；unavailable=直接 503
    SEARCH_DEGRADE_MODE = os.getenv('SEARCH_DEGRADE_MODE', 'fallback')
    # ES 故障后的熔断窗口（秒），窗口内不再探测 ES
    SEARCH_DEGRADE_TTL = int(os.getenv('SEARCH_DEGRADE_TTL', '30'))
    # 降级 LIKE 的最短关键词长度（单个 CJK 字符放行）
    SEARCH_FALLBACK_MIN_LEN = int(os.getenv('SEARCH_FALLBACK_MIN_LEN', '2'))
    # 降级 LIKE 的每页上限
    SEARCH_FALLBACK_MAX_PER_PAGE = int(os.getenv('SEARCH_FALLBACK_MAX_PER_PAGE', '20'))
    # 降级结果（ID+总数）短 TTL 缓存（秒）
    SEARCH_FALLBACK_CACHE_TTL = int(os.getenv('SEARCH_FALLBACK_CACHE_TTL', '10'))

    # ==================== 日志配置 ====================
    LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    @classmethod
    def init_app(cls, app):
        """初始化应用配置"""
        # 创建上传目录
        os.makedirs(cls().UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)

    #========================Feed配置(业务规则)=====================
    #大V判定阈值：粉丝>=该值走拉模式，按压测反推：4*阈值<=redis可承受单帖突发写
    BIG_V_THRESHOLD=int(os.getenv('BIG_V_THRESHOLD','1000'))
    #fanout 异步阈值：粉丝>=该值走 Celery feed 队列异步推送，以下同步推送。
    #约束：FEED_FANOUT_ASYNC_THRESHOLD < BIG_V_THRESHOLD
    FEED_FANOUT_ASYNC_THRESHOLD=int(os.getenv('FEED_FANOUT_ASYNC_THRESHOLD','500'))



