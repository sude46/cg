import logging
import threading
import time
from collections import OrderedDict

from flask import g, request
from flask_jwt_extended import get_jwt, get_jwt_identity
from flask_jwt_extended import verify_jwt_in_request as original_verify_jwt
from flask_jwt_extended.exceptions import (
    JWTExtendedException,
    NoAuthorizationError,
    RevokedTokenError,
)
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.common.exceptions import AuthenticationError, DatabaseError
from core.database import db
from core.extensions import jwt
from utils.redis_util import RedisClient

logger=logging.getLogger(__name__)

#线程安全锁
_revoked_lock=threading.Lock()

# ========== JWT 黑名单 LRU 缓存（减少 Redis QPS）==========
class JWTBlacklistCache:
    """
    线程安全的 LRU 缓存，缓存黑名单查询结果。
    - 正结果（已撤销）：短时间重复请求不查 Redis
    - 负结果（未撤销）：短 TTL，防刚签发的 Token 被漏判
    容量上限 10000 条，超出后淘汰最久未访问的条目。
    """
    def __init__(self, capacity: int = 10000, ttl: float = 10.0):
        self.capacity = capacity
        self.ttl = ttl
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def get(self, jti: str) -> bool:
        """返回 True(已撤销) / False(未撤销) / None(缓存未命中)"""
        with self._lock:
            entry = self._cache.get(jti)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._cache[jti]
                return None
            self._cache.move_to_end(jti)
            return value

    def set(self, jti: str, revoked: bool):
        """写入缓存条目"""
        with self._lock:
            if len(self._cache) >= self.capacity:
                self._cache.popitem(last=False)
            self._cache[jti] = (revoked, time.monotonic() + self.ttl)

    def clear(self):
        with self._lock:
            self._cache.clear()

_blacklist_cache = JWTBlacklistCache()

def is_public_route(path:str,method:str=None):
    '''
    判断是否为公开路由
    '''
    #处理CORS预检
    if method=='OPTIONS':
        return True

    #规范化路径：统一小写并去除多余斜杠
    path=path.lower().rstrip('/')
    if not path:
        path='/'

    #swagger文档和Json
    if path.endswith('/swagger.json') or path.endswith('/swagger-ui'):
        return True
    #静态资源
    if path.startswith('/static/'):
        return True
    #精确匹配
    public_exact={
        '/','/favicon.ico','/ping','/register',
        '/users/register','/users/login','/metrics'
    }
    if path in public_exact:
        return True

    #前缀匹配
    public_prefixes=['/auth','/api/auth','/health']
    for prefix in public_prefixes:
        if path==prefix or path.startswith(prefix+'/'):
            return True
    return False

def init_auth_middleware(app):
    '''初始化认证中间件:JWT黑名单+请求前认证校验+用户注入'''
    #从配置读取Redis客户端
    redis_client=RedisClient.get_conn(for_write=True)
    #使用配置中的key,或默认值
    BLACKLIST_KEY=app.config.get('JWT_BLACKLIST_KEY','jwt:blacklist')
    #默认Token有效期（用于黑名单过期时间)
    DEFAULT_TOKEN_TIL=app.config.get('JWT_ACCESS_TOKEN_EXPIRES',3600*24)

    def _is_token_revoked(jti:str):
        '''检查Token是否被撤销（双层缓存：LRU内存→Redis→内存降级）'''
        if not jti:
            return True

        # 1. LRU 内存缓存（毫秒级，减少 90%+ Redis QPS）
        cached = _blacklist_cache.get(jti)
        if cached is not None:
            return cached

        # 2. 查 Redis
        if redis_client:
            try:
                key=f'{BLACKLIST_KEY}:{jti}'
                revoked = redis_client.exists(key) > 0
                # 写回 LRU 缓存，10s 内不再查 Redis
                _blacklist_cache.set(jti, revoked)
                return revoked
            except RedisError as e:
                logger.error(f'Redis查询失败，降级到内存模式:{e}')
                pass
        # 3. 内存降级模式（Redis 完全不可用时兜底）
        with _revoked_lock:
            revoked_set=getattr(app,'revoked_tokens',set())
            return jti in revoked_set

    @jwt.token_in_blocklist_loader
    def check_is_token_revoked(jwt_header,jwt_payload):
        '''JWT解码时自动调用'''
        jti=jwt_payload.get('jti')
        return _is_token_revoked(jti)
    @app.before_request
    def pre_auth_check():
        '''请求亲认证检查（带资源清理）'''
        if is_public_route(request.path,request.method):
            return
        try:
            #强制校验
            original_verify_jwt(optional=False)
            jwt_data=get_jwt()

            #优先使用get_jwt_identity，兼容多种payload结构
            user_id=jwt_data.get('user_id')or get_jwt_identity()
            if not user_id or not isinstance(user_id,int):
                raise AuthenticationError('Token中用户表示无效')
            #数据库查询带上下问管理确保连接释放
            user=None
            from app.users.models import User
            try:
                user=db.session.query(User).filter(
                    User.id==user_id,
                    User.deleted_at.is_(None)
                ).first()
            except SQLAlchemyError as e:
                logger.error(f'查询用户失败:{user_id},错误：{e}')
                db.session.rollback()
                raise DatabaseError('数据库查询失败')
            finally:
                #去报连接归还到连接池
                db.session.remove()
            if not user:
                raise AuthenticationError('用户不存在或已被删除')
            #用户状态校验
            if not getattr(user,'is_active',True):
                raise AuthenticationError('用户已被禁用')
            #注入全局对象
            g.current_user=user
        except NoAuthorizationError:
            raise AuthenticationError('未检测到 Token，请先登录')
        except RevokedTokenError:
            raise AuthenticationError('Token 已被撤销，请重新登录')
        except JWTExtendedException as e:
            logger.warning(f"JWT 验证失败: {type(e).__name__} - {e}")
            raise AuthenticationError('认证失败')
        except (AuthenticationError, DatabaseError):
            raise  # 自定义异常透传
        except Exception as e:
            logger.error(f'认证校验失败: {e}', exc_info=True)
            raise AuthenticationError('认证服务异常，请稍后重试') from e

    def revoke_token(jti:str,expires_seconds:int=None):
        '''将Token加入黑名单（同步更新 LRU 缓存）'''
        if not jti:
            raise ValueError('无效JTI')
        expire=expires_seconds or DEFAULT_TOKEN_TIL
        # 预热 LRU 缓存：立即标记已撤销
        _blacklist_cache.set(jti, True)
        try:
            if redis_client:
                key=f'{BLACKLIST_KEY}:{jti}'
                redis_client.setex(key,expire,'1')
                logger.info(f'Token已加入Redis黑名单:{jti},TTL:{expire}s')
                return True
        except RedisError as e:
            logger.error(f'redis写入失败，降级到内存:{e}')
        with _revoked_lock:
            if not hasattr(app,'revoked_tokens'):
                app.revoked_tokens=set()
            app.revoked_tokens.add(jti)
            logger.warning(f'Token已加入内存黑名单:{jti}')
            return True

    #挂载到app对象，方便外部调用
    app.revoke_token=revoke_token
    app.is_token_revoked=_is_token_revoked
    logger.info('认证中间件初始化完成')

__all__=['init_auth_middleware']


