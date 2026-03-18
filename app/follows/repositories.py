from typing import Optional, Dict, Any
from sqlalchemy.orm import selectinload,joinedload
from core import db
from app.follows.models import Follow
from app.common.database import pagination_utils


class FollowRepository:
    """关注关系仓储：封装关注/取关的数据访问。"""

    @staticmethod
    def get_relation(follower_id: int, followed_id: int) -> Optional[Follow]:
        """获取某个关注关系（唯一约束）。"""
        return Follow.query.options(joinedload(Follow.follower),joinedload(Follow.followed)).filter_by(follower_id=follower_id, followed_id=followed_id).first()

    @staticmethod
    def create_follow(follower_id: int, followed_id: int) -> Follow:
        """创建关注关系（不提交事务，上层控制 commit/rollback）。"""
        follow = Follow(follower_id=follower_id, followed_id=followed_id)
        db.session.add(follow)
        return follow

    @staticmethod
    def delete_follow(follow: Follow) -> None:
        """删除关注关系（硬删除），不提交事务。"""
        db.session.delete(follow)

    @staticmethod
    def list_following(user_id: int, page: int = 1, size: int = 20) -> Dict[str, Any]:
        """分页获取我关注的人。"""
        query = (
            Follow.query.options(selectinload(Follow.followed))
            .filter_by(follower_id=user_id)
            .order_by(Follow.id.desc())
        )
        return pagination_utils.paginate(query, page=page, per_page=size)

    @staticmethod
    def list_followers(user_id: int, page: int = 1, size: int = 20) -> Dict[str, Any]:
        """分页获取关注我的人。"""
        query = (
            Follow.query.options(selectinload(Follow.follower))
            .filter_by(followed_id=user_id)
            .order_by(Follow.id.desc())
        )
        return pagination_utils.paginate(query, page=page, per_page=size)


follow_repository = FollowRepository()