import logging

from flask_jwt_extended import create_access_token, create_refresh_token

from app.common.database import utcnow
from app.common.exceptions import AuthenticationError, ValidationError
from app.users.cache import UserCache
from app.users.repositories import user_repository
from core import db
from core.metrics import USER_OPERATIONS
from core.security import security_manager

from ..schemas import UserSchema
from .account_service import AccountLockService
from .password_service import password_service
from .token_service import TokenService

logger = logging.getLogger(__name__)


class AuthService:

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
        return {'message': '用户注册成功', 'user': serialized_user}

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

        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)
        user_schema = UserSchema()
        serialized_user = user_schema.dump(user)

        UserCache.set_profile(user.id, serialized_user)
        UserCache.mark_recently_modified(user.id, ttl=5)

        USER_OPERATIONS.labels(action='login', result='success').inc()
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'bearer',
            'expires_in': 3600,
            'user': serialized_user,
        }

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
    def refresh_token(user_id: int) -> dict:
        user = user_repository.get_by_id(user_id)
        if not user or not getattr(user, 'is_active', True):
            raise AuthenticationError('用户不存在或被禁用')
        access_token = create_access_token(identity=user_id)
        USER_OPERATIONS.labels(action='refresh_token', result='success').inc()
        return {'access_token': access_token, 'token_type': 'bearer', 'expires_in': 3600}

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
