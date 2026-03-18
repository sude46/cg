import logging
from flask import request, g, current_app as app
from flask_jwt_extended import verify_jwt_in_request as original_verify_jwt, get_jwt
from flask_jwt_extended.exceptions import JWTExtendedException, NoAuthorizationError, RevokedTokenError
from app.common.exceptions import AuthenticationError,DatabaseError
from app.users.models import User
from core.database import db
from core.extensions import jwt
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)



def verify_jwt_in_request(optional=False):
    """直接调用原生的 JWT 验证函数"""
    return original_verify_jwt(optional=optional)

def is_public_route(path: str) -> bool:
    # 1. 自动放行所有 Swagger 文档和 JSON（一劳永逸）
    if path.endswith('/docs') or path.endswith('/swagger.json'):
        return True
    
    # 2. 静态资源
    if path.startswith('/swaggerui/'):
        return True
    
    # 3. 公开 API（登录注册等）
    public_exact = [
        '/',
        '/favicon.ico',
        '/ping',
        '/register',
        '/users/register',
        '/users/login',
    ]
    if path in public_exact:
        return True
    
    # 4. 公开前缀
    public_prefixes = ['/auth/', '/api/auth/', '/health/']
    for prefix in public_prefixes:
        if path.startswith(prefix):
            return True
    
    return False

def init_auth_middleware(app):
    """初始化认证中间件：JWT黑名单 + 请求前认证校验 + 用户注入"""
    # 从配置读取 Redis 客户端（在 extensions.py 中初始化并存入 app.config）
    redis_client = app.config.get('REDIS_CLIENT')
    BLACKLIST_KEY = 'jwt_blacklist'  # Redis 中黑名单 key

    @jwt.token_in_blocklist_loader
    def check_if_token_is_revoked(jwt_header, jwt_payload):
        """Redis 实现 Token 黑名单"""
        jti = jwt_payload.get('jti')
        if not jti:
            return True  # 无 jti 直接判定为无效
        if redis_client:
            return redis_client.sismember(BLACKLIST_KEY, jti)
        # 降级：内存黑名单（仅开发环境）
        if not hasattr(app, 'revoked_tokens'):
            app.revoked_tokens = set()
        return jti in app.revoked_tokens

    @app.before_request
    def pre_auth_check():
        """请求前认证检查"""
        if is_public_route(request.path):
            return

        try:
            # 强制校验 JWT
            verify_jwt_in_request(optional=False)
            jwt_data = get_jwt()

            user_id = jwt_data.get('user_id')
            if not user_id or not isinstance(user_id, int):
                raise AuthenticationError('Token 中用户标识无效')

            # 数据库查询容错
            try:
                user = db.session.query(User).filter(
                    User.id == user_id,
                    User.is_deleted == False
                ).first()
            except SQLAlchemyError as e:
                logger.error(f'查询用户失败：{str(e)}', exc_info=True)
                raise DatabaseError('用户信息查询失败') from e

            if not user:
                raise AuthenticationError('用户不存在或已被删除')

            # 用户状态校验（示例字段 status，请根据实际模型调整）
            if getattr(user, 'status', None) == 'disabled':
                raise AuthenticationError('账号已被禁用，请联系管理员')

            g.current_user = user

        except NoAuthorizationError:
            raise AuthenticationError('未检测到 Token，请先登录')
        except RevokedTokenError:
            raise AuthenticationError('Token 已被撤销，请重新登录')
        except JWTExtendedException as e:
            app.logger.warning(f"JWT 验证失败: {type(e).__name__} - {str(e)}")
            raise AuthenticationError("认证失败", code=401)
        except (AuthenticationError, DatabaseError):
            raise  # 自定义异常直接抛出
        except Exception as e:
            logger.error(f'认证校验失败：{str(e)}', exc_info=True)
            raise AuthenticationError('认证失败，请重新登录') from e

    def revoke_token(jti: str, expire_seconds: int = 31536000):
        """将 Token 加入黑名单（Redis 或内存）"""
        if not jti:
            raise ValueError('无效的 JTI')
        if redis_client:
            redis_client.sadd(BLACKLIST_KEY, jti)
            redis_client.expire(BLACKLIST_KEY, expire_seconds)
        else:
            if not hasattr(app, 'revoked_tokens'):
                app.revoked_tokens = set()
            app.revoked_tokens.add(jti)
            logger.warning('Redis 未配置，使用内存黑名单（生产环境禁止）')

    # 将 revoke_token 挂载到 app 方便调用
    app.revoke_token = revoke_token

__all__ = ['init_auth_middleware']
