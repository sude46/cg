from core import db
from core.security import security_manager  # ✅ 使用统一的安全管理器
import logging
from flask_jwt_extended import create_access_token, create_refresh_token
from ..models import User
from app.users.repositories import user_repository
from app.common.exceptions import ValidationError, AuthenticationError
from datetime import datetime, timezone
from ..schemas import UserSchema
from .password_service import PasswordService
from .account_service import AccountLockService
from .token_service import TokenService

class AuthService:

    def __init__(
        self,
        password_service: 'PasswordService' = None,
        account_lock_service: 'AccountLockService' = None,
        token_service: 'TokenService' = None,
    ):
        # 依赖注入：通过构造函数传入依赖，便于测试和替换
        self.password_svc = password_service or PasswordService()
        self.lock_svc = account_lock_service or AccountLockService()
        self.token_svc = token_service or TokenService()



    def register_user(self, username: str, email: str, password: str):
        
        # 检查是否存在（通过仓储）
        if user_repository.get_by_username(username):
            raise ValidationError('用户名已存在')
        if user_repository.get_by_email(email):
            raise ValidationError('邮箱已存在')
        validation=security_manager.password_validator.validate(password)
        if not validation['is_valid']:
            raise ValidationError(f'密码不符合要求: {validation["issues"]}')

        # 创建用户（仓储负责构造对象并 add 到 session，is_不提交）
        user = user_repository.create_user(username=username, email=email)
        user.password_hash = self.password_svc.hash_password(password)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        user_schema = UserSchema()
        serialized_user=user_schema.dump(user)
        return {'message': '用户注册成功', 'user': serialized_user}
    
    
    def authenticate_user(self,username: str, password: str) -> dict:
        user = user_repository.get_by_username(username)
        #查询用户
        if not user:
            raise AuthenticationError('用户名或密码错误')
        #校验账户是否被锁定
        if self.lock_svc.is_locked(user):
            raise AuthenticationError('账户已锁定，20分钟后再试')
        #验证密码
        if not self.password_svc.verify_password(user.password_hash,password):
            self.lock_svc.record_failed_attempt(user)
            db.session.commit()
            raise AuthenticationError('用户名或密码错误')
        #校验账户状态
        if not getattr(user, 'is_active', True):
            raise AuthenticationError('用户账户被禁用')
        
        # 登录成功，重置失败计数和锁定状态
        self.lock_svc.reset_attempts(user)
        # 更新最后登录时间
        user.last_login = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()

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
    
    #密码重置：生成重置令牌
    def generate_password_reset_token(self,user_id:int):
        return self.token_svc.generate_reset_token(user_id)
    #密码重置：验证令牌+更新密码
    def reset_password(self,token:str,new_password:str):
        user_id=self.token_svc.verify_reset_token(token)
        if not user_id:
            raise ValidationError('无效或过期的重置令牌')
        user=user_repository.get_by_id(user_id)
        if not user:
            raise ValidationError('用户不存在')
        #校验密码是否重复使用
        if self.password_svc.is_password_reused(user,new_password):
            raise ValidationError('不能使用最近5使用过的密码')
        self.password_svc.update_password(user,new_password)
        db.session.commit()
        return {'message':'密码重置成功'}
    

    
    def refresh_token(self, user_id: int) -> dict:
        user = user_repository.get_by_id(user_id)
        if not user or not getattr(user, 'is_active', True):
            raise AuthenticationError('用户不存在或被禁用')
        access_token = create_access_token(identity=user_id)
        return {'access_token': access_token, 'token_type': 'bearer', 'expires_in': 3600}

    def get_current_user(self, user_id: int) -> dict:
        user = user_repository.get_by_id(user_id)
        if not user or not getattr(user, 'is_active', True):
            raise AuthenticationError('用户不存在或被禁用')
        user_schema = UserSchema()
        serialized_user = user_schema.dump(user)
        return {'user': serialized_user}
