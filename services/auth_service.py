from core import db,bcrypt,jwt
from app.users.models import User
from app.common import (ValidationError,ResourceNotFoundError,DatabaseError,PASSWORD_RULES)
from flask_jwt_extended import create_access_token,create_refresh_token
from datetime import timedelta
import re
import logging

logger=logging.getLogger(__name__)

class AuthService:
    @staticmethod
    def register(username:str,email:str,password:str)->dict:
        '''用户注册'''
        if not username or len(username)<3 or len(username)>20:
            raise ValidationError('用户名长度必须为3-20字符')
        if not re.match(r'^[a-zA-Z0-9_]+\.[a-zA-Z0-9-.]+$',email):
            raise ValidationError('邮箱格式无效')
        #验证密码规则
        if len(password)<PASSWORD_RULES['MIN_LENGTH']or len(password)>PASSWORD_RULES['MAX_LENGTH']:
            raise ValidationError(f"密码长度必须为：{PASSWORD_RULES['MIN_LENGTH']}-{PASSWORD_RULES['MAX_LENGTH']}字符")
        if PASSWORD_RULES['REQUIRE_UPPERCASE'] and not re.search(r'[A-Z]',password):
            raise ValidationError('密码必须包含大写字母')
        if PASSWORD_RULES['REQUIRED_DIGIT'] and not re.search(r'[0-9',password):
            raise ValidationError('密码必须包含数字')
        if User.query.filter_by(username=username).first():
            raise ValidationError('用户名已被占用')
        if User.query.filter_by(email=email).first():
            raise ValidationError('邮箱已被注册')
        try:
            #加密密码
            hashed_password=bcrypt.generate_password_hash(password).decode('utf-8')
            #创建用户
            user=User(
                    username=username,
                    email=email,
                    password_hash=hashed_password
                    )
            db.session.add(user)
            db.session.commit()
            logger.info(f'用户注册成功:{username}({user.id})')
            return {
                    'message':'注册成功',
                    'user_id':user.id,
                    'username':user.username
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f'注册失败:{str(e)}')
            raise DatabaseError()
    
    @staticmethod
    def login(login_id:str,password:str):
        '''用户登录'''
        user=User.query.filter(
                (User.username==login_id)|(User.email==login_id)
                ).first()
        if not user:
            raise ResourceNotFoundError('用户')
        if not bcrypt.check_password_hash(user.password_hash,password):
            raise ValidationError('密码错误')
        access_token=create_access_token(
                identity=user.id,
                expires_delta=timedelta(hours=1)
                )
        refresh_token=create_refresh_token(
                identity=user.id,
                expires_delta=timedelta(days=7)
                )
        logger.info(f'用户登录成功:{user.username}({user.id})')
        return {
                'access_token':access_token,
                'refresh_token':refresh_token,
                'user':{
                    'id':user.id,
                    'username':user.username
                    }
                }
    @staticmethod
    def refresh_token(user_id:int):
        if not User.query.get(user_id):
            raise ResourceNotFoundError('用户')
        new_access_token=create_access_token(
                identity=user_id,
                expires_delta=timedelta(hours=1)
                )
        return {'access_token':new_access_token}



