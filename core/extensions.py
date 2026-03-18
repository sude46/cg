from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager,get_jwt
from flask_mail import Mail
from flask import current_app
from redis import Redis,ConnectionPool


#redis(带连接池，jwt黑名单依赖)
redis_pool=None
redis_client=None

#认证相关(JWT依赖Redistribution，须在Redis后定义)
jwt=JWTManager()

#其它无依赖扩展
bcrypt=Bcrypt()
mail=Mail()


def init_redis(app):
    """初始化Redis连接池(解决平凡创建/关闭连接问题)"""
    global redis_pool,redis_client
    #配置读取Redis参数
    redis_config={
        "host":app.config.get("REDIS_HOST","localhost"),
        "port":app.config.get("REDIS_PORT",6379),
        "db":app.config.get("REDIS_DB",0),
        "password":app.config.get("REDIS_PASSWORD",""),
        "decode_responses":True
    }

    #创建连接池（核心优化点）
    redis_pool=ConnectionPool(**redis_config)
    redis_client=Redis(connection_pool=redis_pool)

    #验证连接
    try:
        redis_client.ping()
        app.logger.info("Redis连接池初始化成功")
    except Exception as e:
        app.logger.error(f"Redis连接池初始化失败:{str(e)}")
        raise e
    app.config['REDIS_CLIENT'] = redis_client
    
def init_jwt(app):
    "初始化JWT（添加黑名单校验你，解决登出后Token依旧可用问题）"
    jwt.init_app(app)

    #JWT黑名单校验回调（核心安全修复）
    @jwt.token_in_blocklist_loader
    def check_if_token_blacklist(jwt_header,jwt_payload):
        jti=jwt_payload["jti"] #JWT唯一标识
        #从Redis黑名单中查询
        return redis_client.sismember("jwt_blacklist",jti)
    
    #添加黑名单Token提示
    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header,jwt_payload):
        return {'msg':"该Token已被等处，无法使用"},401
    
    app.logger.info("JWT初始化完成(已启用 黑名单校验)")

def init_bcrypt(app):
    """初始化Bcrypt"""
    bcrypt.init_app(app)
    #验证rounds配置生效(生产环境可删除)
    app.logger.info(f"bcrypt加密轮次:{app.config.get('BCRYPT_LOG_ROUNDS')}")

def init_mail(app):
    """初始化mail"""
    mail.init_app(app)
    app.logger.info("mail初始化完成")

def init_extensions(app):
    """统一初始化所有扩展（按以来顺序执行，解决初始化顺序混乱问题)"""
    init_redis(app)
    init_jwt(app)
    init_bcrypt(app)
    init_mail(app)

    app.logger.info("所有扩展初始化完成")






