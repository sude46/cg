from core import db
import logging
from flask_jwt_extended import create_access_token, create_refresh_token
from .models import User
from app.users.repositories import user_repository
from app.common.exceptions import ValidationError, AuthenticationError
from utils.validators import validate_username, validate_password, validate_email
from datetime import datetime, timezone
from .schemas import UserSchema
from utils.security_utils import desensitize_password

logger=logging.getLogger(__name__)

class AuthService:
    @staticmethod
    def register_user(username: str, email: str, password: str):
        if not validate_username(username):
            raise ValidationError('用户名格式无效')
        if not validate_email(email):
            raise ValidationError('邮箱格式无效')
        if not validate_password(password):
            raise ValidationError('密码必须包含字母数字，且长度至少8位')

        # 检查是否存在（通过仓储）
        if user_repository.get_by_username(username):
            raise ValidationError('用户名已存在')
        if user_repository.get_by_email(email):
            raise ValidationError('邮箱已存在')

        # 创建用户（仓储负责构造对象并 add 到 session，不提交）
        user = user_repository.create_user(username=username, email=email)
        user.set_password(password)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        user_schema = UserSchema()
        serialized_user=user_schema.dump(user)
        return {'message': '用户注册成功', 'user': serialized_user}
    
    @staticmethod
    def authenticate_user(username: str, password: str) -> dict:
        user = user_repository.get_by_username(username)
        if not user or not user.check_password(password):
            raise AuthenticationError('用户名或密码错误')
        if not getattr(user, 'is_active', True):
            raise AuthenticationError('用户账户已被禁用')

        # 更新最后登录时间
        user.last_login = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update last login for user {user.id}: {str(e)}")

        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)
        user_schema = UserSchema()
        serialized_user = user_schema.dump(user)

        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'bearer',
            'expires_in': 3600,
            'user': serialized_user,
        }

    @staticmethod
    def refresh_token(user_id: int) -> dict:
        user = user_repository.get_by_id(user_id)
        if not user or not getattr(user, 'is_active', True):
            raise AuthenticationError('用户不存在或被禁用')
        access_token = create_access_token(identity=user_id)
        return {'access_token': access_token, 'token_type': 'bearer', 'expires_in': 3600}

    @staticmethod
    def get_current_user(user_id: int) -> dict:
        user = user_repository.get_by_id(user_id)
        if not user or not getattr(user, 'is_active', True):
            raise AuthenticationError('用户不存在或被禁用')
        user_schema = UserSchema()
        serialized_user = user_schema.dump(user)
        return {'user': serialized_user}
