from typing import Optional
import logging
from core.database import db 
from app.users.models import User
from app.common.database import pagination_utils
from .schemas import UserListSchema

logger = logging.getLogger(__name__)

class UserRepository:
    """用户仓储：封装 User 模型的所有数据库访问."""

    @staticmethod
    def get_by_id(user_id: int):
        """根据 ID 获取未删除的用户"""
        return User.query.filter_by(id=user_id, is_deleted=False).first()

    @staticmethod
    def get_by_username(username: str):
        """根据用户名获取未删除的用户"""
        return User.query.filter_by(username=username, is_deleted=False).first()

    @staticmethod
    def get_by_email(email: str):
        """根据邮箱获取未删除的用户"""
        return User.query.filter_by(email=email, is_deleted=False).first()

    @staticmethod
    def soft_delete(user: User) -> None:
        """软删除用户"""
        user.is_deleted = True
        db.session.add(user)

    @staticmethod
    def create_user(**fields):
        user = User(**fields)
        db.session.add(user)
        return user

    @staticmethod
    def list_users(page: int = 1, per_page: int = 20) -> dict:
        '''分页查询用户列表：返回{'items':[User,...],'pagination':{....}}'''
        query=User.query.filter_by(is_active=True, is_deleted=False).order_by(User.id.desc())

        #使用分页工具
        result=pagination_utils.paginate(query,page=page,per_page=per_page)
        
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }
    @staticmethod
    def search_by_keyword(keyword:str,page:int=1,per_page:int=20):
        '''根据关键词搜索用户（排除已删除）'''
        query=User.query.filter(
            User.username.ilike(f'%{keyword}%'),
            User.is_deleted == False
        ).order_by(User.username)
        result=pagination_utils.paginate(query,page=page,per_page=per_page)
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }

user_repository = UserRepository()
