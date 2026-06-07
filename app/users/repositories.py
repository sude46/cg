from typing import Optional
from datetime import datetime, timezone
from app.common.database import utcnow
import logging
from core.database import db
from app.users.models import User
from app.common.database import pagination_utils, get_read_session
from .schemas import UserListSchema
from sqlalchemy import update, func

logger = logging.getLogger(__name__)


class UserRepository:
    """用户仓储：封装 User 模型的所有数据库访问."""

    @staticmethod
    def _read_session():
        return get_read_session()

    @staticmethod
    def get_by_id(user_id: int, force_master: bool = False) -> Optional[User]:
        """根据 ID 获取未删除的用户"""
        session = db.session if force_master else UserRepository._read_session()
        return session.query(User).filter(
            User.id == user_id,
            User.deleted_at.is_(None)
        ).first()

    @staticmethod
    def get_by_username(username: str, force_master: bool = False) -> Optional[User]:
        """根据用户名获取未删除的用户"""
        session = db.session if force_master else UserRepository._read_session()
        return session.query(User).filter(
            User.username == username,
            User.deleted_at.is_(None)
        ).first()

    @staticmethod
    def get_by_email(email: str, force_master: bool = False) -> Optional[User]:
        """根据邮箱获取未删除的用户"""
        session = db.session if force_master else UserRepository._read_session()
        return session.query(User).filter(
            User.email == email,
            User.deleted_at.is_(None)
        ).first()

    @staticmethod
    def soft_delete(user: User) -> None:
        """软删除用户"""
        user.deleted_at = utcnow()

    @staticmethod
    def create_user(**fields):
        user = User(**fields)
        db.session.add(user)
        return user

    @staticmethod
    def list_users(page: int = 1, per_page: int = 20) -> dict:
        """分页查询用户列表"""
        session = UserRepository._read_session()
        query = session.query(User).filter(
            User.is_active.is_(True),
            User.deleted_at.is_(None)
        ).order_by(User.id.desc())
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }

    @staticmethod
    def search_by_keyword(keyword: str, page: int = 1, per_page: int = 20):
        """根据关键词搜索用户（排除已删除）"""
        session = UserRepository._read_session()
        query = session.query(User).filter(
            User.username.ilike(f'%{keyword}%'),
            User.deleted_at.is_(None)
        ).order_by(User.username)
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }
    
    @staticmethod
    def increment_following_count(user_id: int) -> None:
        """原子更新关注计数 +1（写主库）"""
        db.session.execute(
            update(User).where(User.id == user_id).values(
                following_count=User.following_count + 1
            )
        )

    @staticmethod
    def decrement_following_count(user_id: int) -> None:
        """原子更新关注计数 -1（保底不小于 0）"""
        db.session.execute(
            update(User).where(User.id == user_id).values(
                following_count=func.greatest(User.following_count - 1, 0)
            )
        )

    @staticmethod
    def increment_follower_count(user_id: int) -> None:
        """原子更新粉丝计数 +1"""
        db.session.execute(
            update(User).where(User.id == user_id).values(
                follower_count=User.follower_count + 1
            )
        )

    @staticmethod
    def decrement_follower_count(user_id: int) -> None:
        """原子更新粉丝计数 -1（保底不小于 0）"""
        db.session.execute(
            update(User).where(User.id == user_id).values(
                follower_count=func.greatest(User.follower_count - 1, 0)
            )
        )

user_repository = UserRepository()
