import os
import secrets
import warnings
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


class BaseConfig:
    SECRET_KEY=os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        warnings.warn("SECRET_KEY未从环境配置！生产环境必须设置该环境变量",UserWarning)
        SECRET_KEY='dev-key-'+secrets.token_hex(32)
    JWT_SECRET_KEY=os.getenv('JWT_SECRET_KEY')
    if not JWT_SECRET_KEY:
        warnings.warn("JWT_SECRET_KEY未从环境变量配置！生产环境必须设置该环境变量", UserWarning)
        JWT_SECRET_KEY='jwt-dev-only'+secrets.token_hex(32)
                
    DEBUG=False
    TESTING=False
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS=False
    SQLALCHEMY_ECHO=False

    JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES=timedelta(days=30)

    
    @property
    def UPLOAD_FOLDER(self):
        # 默认上传目录相对于项目根的 app/static/uploads
        base_dir = os.path.abspath(os.path.dirname(__file__))
        project_root = os.path.abspath(os.path.join(base_dir, '..'))
        return os.path.join(project_root, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH=16*1024*1024 #16MB
    
    #Redis配置
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))  # 转成整数
    REDIS_DB = int(os.getenv("REDIS_DB", 0))          # 转成整数
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "") 
    REDIS_URL=os.getenv('REDIS_URL')or 'redis://localhost:6379/0'
    REDIS_CONN=REDIS_URL
    
    #邮件配置
    MAIL_SERVER=os.getenv('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT=int(os.getenv('MAIL_PORT')or 587)
    MAIL_USE_TLS=True
    MAIL_USERNAME=os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD')

    #定义时区os.environ.get('TIMEZONE','UTC')
    TIMEZONE=os.getenv('TIMEZONE','UTC')

    #SQLALCHEMY引擎配置：仅保留 pool_pre_ping，移除 timezone
    SQLALCHEMY_ENGINE_OPTIONS={
        'pool_pre_ping': True
    }

    #分页配置
    PAGE_SIZE=20
    MAX_PAGE_SIZE=100
    
    #安全配置
    SESSION_COOKIE_SECURE=False
    SESSION_COOKIE_HTTPONLY=True
    SESSION_COOKIE_SAMESITE='Lax'
    
    #密码策略
    PASSWORD_MIN_LENGTH=8
    PASSWORD_REQUIRE_UPPERCASE=True
    PASSWORD_REQUIRE_LOWERCASE=True
    PASSWORD_REQUIRED_NUMBERS=True
    PASSWORD_REQUIRED_SYMBOLS=False

    # ========== 新增：CORS配置（可选） ==========
    CORS_RESOURCES = os.getenv("CORS_RESOURCES", r"/*")  # 允许所有接口跨域
    CORS_SUPPORTS_CREDENTIALS = True  # 可选：允许跨域携带Cookie（前端需要的话加）

    #速率限制
    RATE_LIMIT_DEFAULT = ["10 per minute", "100 per hour"]
    RATE_LIMIT_AUTH=10 #认证相关接口限制

    #Bcrypt加密轮次
    BCRYPT_LOG_ROUNDS=int(os.getenv('BCRYPT_LOG_ROUNDS',12))
    BCRYPT_LOG_ROUNDS=BCRYPT_LOG_ROUNDS
    #登录安全配置
    LOGIN_MAX_ATTEMPTS = 5  # 登录失败最大次数（触发验证码/锁定）
    LOGIN_LOCK_DURATION = 300  # 登录失败锁定时长（秒，5分钟）
    CAPTCHA_EXPIRY = 180  # 验证码有效期（秒，3分钟）
    CAPTCHA_LENGTH = 6  # 验证码长度（数字/字母组合）

    #日志配置
    LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    #日志文件名称
    INFO_LOG_FILE = "info.log"
    ERROR_LOG_FILE = "error.log"
    #日志轮转配置：按日轮转，保留7天日志
    LOG_ROTATE_WHEN = "midnight"  #每日午夜轮转
    LOG_ROTATE_INTERVAL = 1  #轮转间隔为1天
    LOG_ROTATE_BACKUP_COUNT = 7  #保留7天日志
    #日志字段格式（包含核心需求：时间、等级、请求id、用户id、路径、耗时）
    LOG_FORMAT="%(asctime)s%(levelname)s %(request_id)s %(user_id)s %(elapsed_time)s %(message)s"
    
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR,exist_ok=True)

    @classmethod
    def init_app(cls, app):
        app.config['TIMEZONE'] = cls.TIMEZONE
        app.config['JSON_AS_ASCII'] = False  # 额外优化：支持中文JSON

        # 优先从 app.config 获取
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
        # 若未获取到，则实例化配置类，触发 property
        if db_uri is None:
            config_instance = cls()
            db_uri = config_instance.SQLALCHEMY_DATABASE_URI

        # 类型检查，防止 property 泄漏
        if not isinstance(db_uri, str):
            raise RuntimeError(
                f"无法获取有效的数据库 URI，得到类型 {type(db_uri)}，值：{db_uri}"
            )

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(db_uri, **cls.SQLALCHEMY_ENGINE_OPTIONS)
        Session = sessionmaker(bind=engine)
        app.db_session = Session

        app.config['BCRYPT_LOG_ROUNDS'] = cls.BCRYPT_LOG_ROUNDS
        app.config['JWT_SECRET_KEY'] = cls.JWT_SECRET_KEY

