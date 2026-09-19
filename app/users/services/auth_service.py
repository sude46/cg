import logging
import time

from flask_jwt_extended import create_access_token, create_refresh_token, decode_token

from app.common.database import utcnow
from app.common.exceptions import AuthenticationError, ResourceNotFoundError, ValidationError
from app.users.cache import UserCache
from app.users.repositories import user_repository
from core import db
from core.metrics import USER_OPERATIONS
from core.redis_cache import redis_cache
from core.security import security_manager

from ..schemas import UserSchema
from .account_service import AccountLockService
from .password_service import password_service
from .token_service import TokenService

logger = logging.getLogger(__name__)


class AuthService:
    # ============ Refresh Token 轮换 / 复用检测 ============
    # 会话族：一次登录一个 fid；Redis 保存当前有效的 refresh jti
    REFRESH_FAMILY_KEY = 'refresh:{fid}'
    # 宽限窗口：旧 refresh 在窗口内重用视为网络重试/多 tab，返回与新 token 相同的结果
    REFRESH_GRACE_KEY = 'refresh:{fid}:grace:{jti}'
    AUTH_VER_KEY = 'auth:ver:{uid}'
    REFRESH_GRACE_SECONDS = 20

    @staticmethod
    def _refresh_ttl() -> int:
        from flask import current_app
        exp = current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES')
        return int(exp.total_seconds()) if hasattr(exp, 'total_seconds') else int(exp or 30 * 86400)

    @staticmethod
    def _auth_version(user_id: int) -> int:
        """用户 token 版本号；Redis 不可用时降级为 0。"""
        try:
            return int(redis_cache.get(AuthService.AUTH_VER_KEY.format(uid=user_id), for_write=True) or 0)
        except Exception as e:
            logger.warning('读取 token_version 失败（降级为0）: %s', e)
            return 0

    @staticmethod
    def _start_session(user) -> dict:
        """登录/注册建立会话：签发 access+refresh（含 fid/ver）并登记 family。"""
        from uuid import uuid4
        fid = uuid4().hex
        ver = AuthService._auth_version(user.id)
        access = create_access_token(identity=user.id, additional_claims={'ver': ver, 'fid': fid})
        refresh = create_refresh_token(identity=user.id, additional_claims={'ver': ver, 'fid': fid})
        try:
            jti = decode_token(refresh)['jti']
            redis_cache.set_exact(
                AuthService.REFRESH_FAMILY_KEY.format(fid=fid), jti, AuthService._refresh_ttl()
            )
        except Exception as e:
            logger.warning('登记 refresh 会话失败（降级，不轮换）: %s', e)
        return {
            'access_token': access,
            'refresh_token': refresh,
            'token_type': 'bearer',
            'expires_in': 3600,
        }

    @staticmethod
    def register_user(username: str, email: str, password: str):
        if user_repository.get_by_username(username):
            raise ValidationError('用户名已存在')
        if user_repository.get_by_email(email):
            raise ValidationError('邮箱已存在')
        validation = security_manager.password_validator.validate(password)
        if not validation['is_valid']:
            raise ValidationError(f'密码不符合要求: {validation["issues"]}')

        user = user_repository.create_user(username=username, email=email)
        user.password_hash = password_service.hash_password(password)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        user_schema = UserSchema()
        serialized_user = user_schema.dump(user)
        UserCache.set_profile(user.id, serialized_user)
        UserCache.set_by_username(user.username, user.id)
        UserCache.set_by_email(user.email, user.id)
        UserCache.mark_recently_modified(user.id, ttl=5)
        USER_OPERATIONS.labels(action='register', result='success').inc()
        tokens = AuthService._start_session(user)
        return {
            'message': '用户注册成功',
            'user': serialized_user,
            **tokens,
        }

    @staticmethod
    def authenticate_user(username: str, password: str) -> dict:
        user = user_repository.get_by_username(username)
        if not user:
            raise AuthenticationError('用户名或密码错误')
        if AccountLockService.is_locked(user.id):
            raise AuthenticationError('账户已锁定，20分钟后再试')
        if not password_service.verify_password(user.password_hash, password):
            AccountLockService.record_failed_attempt(user.id)
            raise AuthenticationError('用户名或密码错误')
        if not getattr(user, 'is_active', True):
            raise AuthenticationError('用户账户被禁用')

        AccountLockService.reset_attempts(user.id)
        user.last_login = utcnow()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        user_schema = UserSchema()
        serialized_user = user_schema.dump(user)

        UserCache.set_profile(user.id, serialized_user)
        UserCache.mark_recently_modified(user.id, ttl=5)

        USER_OPERATIONS.labels(action='login', result='success').inc()
        tokens = AuthService._start_session(user)
        return {**tokens, 'user': serialized_user}

    @staticmethod
    def generate_password_reset_token(user_id: int):
        return TokenService.generate_tokens(user_id)

    @staticmethod
    def reset_password(token: str, new_password: str):
        user_id = TokenService.verify_reset_token(token)
        if not user_id:
            raise ValidationError('无效或过期的重置令牌')
        user = user_repository.get_by_id(user_id)
        if not user:
            raise ValidationError('用户不存在')
        if password_service.is_password_reused(user, new_password):
            raise ValidationError('不能使用最近5使用过的密码')
        password_service.update_password(user, new_password)
        db.session.commit()

        UserCache.double_invalidate(user.id, username=user.username, email=user.email)
        USER_OPERATIONS.labels(action='reset_password', result='success').inc()
        return {'message': '密码重置成功'}

    @staticmethod
    def refresh_tokens(user_id: int, claims: dict) -> dict:
        """刷新令牌：轮换 + 复用检测（带宽限窗口；Redis 故障时降级不轮换）。"""
        fid = claims.get('fid')
        old_jti = claims.get('jti')
        ver = int(claims.get('ver', 0) or 0)
        if not fid or not old_jti:
            # 老 token 无 fid，无法追踪族，强制重新登录
            raise AuthenticationError('登录状态已失效，请重新登录')

        user = user_repository.get_by_id(user_id, force_master=True)
        if not user or not getattr(user, 'is_active', True):
            raise AuthenticationError('用户不存在或被禁用')

        # 全局版本校验（改密/封禁后旧 token 全失效）；Redis 故障时降级跳过
        try:
            current_ver = int(
                redis_cache.get(AuthService.AUTH_VER_KEY.format(uid=user_id), for_write=True) or 0
            )
            if ver != current_ver:
                raise AuthenticationError('登录状态已失效，请重新登录')
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error('Redis 不可用，refresh 降级：跳过 token_version 校验: %s', e)

        family_key = AuthService.REFRESH_FAMILY_KEY.format(fid=fid)
        grace_key = AuthService.REFRESH_GRACE_KEY.format(fid=fid, jti=old_jti)

        new_access = create_access_token(
            identity=user_id, additional_claims={'ver': ver, 'fid': fid}
        )
        new_refresh = create_refresh_token(
            identity=user_id, additional_claims={'ver': ver, 'fid': fid}
        )
        try:
            new_jti = decode_token(new_refresh)['jti']
        except Exception:
            new_jti = ''

        lua = """
        local cur = redis.call('GET', KEYS[1])
        if not cur then return -1 end
        if cur ~= ARGV[1] then return 0 end
        redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
        return 1
        """
        try:
            r = redis_cache.eval(lua, 1, family_key, old_jti, new_jti, AuthService._refresh_ttl())
        except Exception as e:
            # 条件②：Redis 故障降级——只发新 access，不做轮换
            logger.error('Redis 不可用，refresh 降级为不轮换: %s', e)
            return {'access_token': new_access, 'token_type': 'bearer', 'expires_in': 3600}

        if r == -1:
            raise AuthenticationError('登录已过期，请重新登录')

        if r == 0:
            # 条件①：疑似复用 -> 宽限期内返回与上次轮换相同的结果
            cached = AuthService._get_grace_result(grace_key)
            if cached:
                return cached
            time.sleep(0.05)  # 极端并发：给获胜请求写入宽限结果的时间
            cached = AuthService._get_grace_result(grace_key)
            if cached:
                return cached
            # 超过宽限窗口：判定复用攻击，整族作废
            try:
                redis_cache.delete(family_key)
            except Exception:
                pass
            logger.warning('refresh token 复用 detected: user=%s fid=%s', user_id, fid)
            raise AuthenticationError('检测到令牌复用，请重新登录')

        result = {
            'access_token': new_access,
            'refresh_token': new_refresh,
            'token_type': 'bearer',
            'expires_in': 3600,
        }
        try:
            redis_cache.set_exact(grace_key, result, AuthService.REFRESH_GRACE_SECONDS)
        except Exception:
            pass
        USER_OPERATIONS.labels(action='refresh_token', result='success').inc()
        return result

    @staticmethod
    def _get_grace_result(grace_key: str):
        try:
            cached = redis_cache.get(grace_key, for_write=True)
            if isinstance(cached, dict) and cached.get('access_token'):
                return cached
        except Exception:
            pass
        return None

    @staticmethod
    def get_current_user(user_id: int) -> dict:
        if UserCache.is_recently_modified(user_id):
            user = user_repository.get_by_id(user_id, force_master=True)
            if not user or not getattr(user, 'is_active', True):
                raise AuthenticationError('用户不存在或被禁用')
            user_schema = UserSchema()
            serialized_user = user_schema.dump(user)
            UserCache.set_profile(user_id, serialized_user)
            return {'user': serialized_user}

        cached = UserCache.get_profile(user_id)
        if cached:
            return {'user': cached}

        user = user_repository.get_by_id(user_id, force_master=False)
        if not user or not getattr(user, 'is_active', True):
            raise AuthenticationError('用户不存在或被禁用')
        user_schema = UserSchema()
        serialized_user = user_schema.dump(user)
        UserCache.set_profile(user_id, serialized_user)
        return {'user': serialized_user}

    @staticmethod
    def get_public_profile(target_id:int,current_user_id:int | None=None) -> dict:
        """获取用户公开资料（脱敏；公开资料走独立缓存，不复用含 email 的 profile）"""
        from app.follows.services import FollowService

        from ..schemas import public_user_schema

        profile=UserCache.get_public_profile(target_id)
        if not profile:
            force_master=UserCache.is_recently_modified(target_id)
            user=user_repository.get_by_id(target_id,force_master=force_master)
            if not user or not getattr(user,'is_active',True):
                raise ResourceNotFoundError('用户不存在')
            profile=public_user_schema.dump(user)
            profile['post_count']=user.posts.filter_by(deleted_at=None).count()
            UserCache.set_public_profile(target_id,profile)

        if current_user_id:
            profile['is_me']=(int(current_user_id)==int(target_id))
            profile['is_following']=(
                False if profile['is_me']
                else FollowService.is_following(int(current_user_id),target_id)
            )
        return {'user':profile}

    @staticmethod
    def update_profile(user_id:int,data:dict) -> dict:
        """更新当前用户资料（bio/avatar_url/username/email）"""
        from app.common.exceptions import DatabaseError
        user=user_repository.get_by_id(user_id,force_master=True)
        if not user or not getattr(user,'is_active',True):
            raise ResourceNotFoundError("用户不存在")

        old_username=user.username
        old_email=user.email
        new_username=(data.get('username') or '').strip() or None
        new_email=(data.get('email') or '').strip() or None

        if new_username and new_username!=old_username:
            if user_repository.get_by_username(new_username,force_master=True):
                raise ValidationError('用户名已存在')
            user.username=new_username
        if new_email and new_email!=old_email:
            if user_repository.get_by_email(new_email,force_master=True):
                raise ValidationError('邮箱已存在')
            user.email=new_email
        if "bio" in data:
            user.bio=data['bio']
        if 'avatar_url' in data:
            user.avatar_url=data['avatar_url']

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"更新资料失败:{e}")
            raise DatabaseError("更新资料失败")

        # 失效 profile/public + 旧/新用户名、邮箱索引
        UserCache.double_invalidate(user.id,username=old_username,email=old_email)
        if new_username:
            UserCache.invalidate_by_username(new_username)
        if new_email:
            UserCache.invalidate_by_email(new_email)
        UserCache.mark_recently_modified(user.id,ttl=5)
        USER_OPERATIONS.labels(action='update_profile', result='success').inc()
        return {'user':UserSchema().dump(user)}

    @staticmethod
    def change_password(user_id:int,old_password:str,new_password:str) -> dict:
        """修改密码(带历史校验)"""
        from app.common.exceptions import DatabaseError
        user=user_repository.get_by_id(user_id,force_master=True)
        if not user:
            raise ResourceNotFoundError("用户不存在")
        if not password_service.verify_password(user.password_hash,old_password):
            raise AuthenticationError("原密码错误")
        if old_password == new_password:
            raise ValidationError("新密码不能与原密码相同")
        if password_service.is_password_reused(user,new_password):
            raise ValidationError("不能使用最近使用过的密码")
        password_service.update_password(user,new_password)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"修改密码失败:{e}")
            raise DatabaseError("修改密码失败")
        UserCache.double_invalidate(user.id)
        # 改密后提升 token_version：所有旧 access/refresh 立即失效（前端需重新登录）
        try:
            redis_cache.increment(AuthService.AUTH_VER_KEY.format(uid=user.id))
        except Exception as e:
            logger.error('提升 token_version 失败（改密后旧 token 可能未失效）: %s', e)
        USER_OPERATIONS.labels(action='change_password', result='success').inc()
        return {'message':'密码修改成功'}

    @staticmethod
    def search_users(keyword: str, page: int = 1, per_page: int = 20) -> dict:
        """按用户名搜索用户（脱敏，绝不返回 email）。"""
        from ..schemas import public_user_schema

        keyword = (keyword or '').strip()[:50]
        result = user_repository.search_by_keyword(keyword, page=page, per_page=per_page)
        items = public_user_schema.dump(result.get('items', []), many=True)
        USER_OPERATIONS.labels(action='search', result='success').inc()
        return {'items': items, 'pagination': result.get('pagination', {})}
