from typing import Optional, Dict, Any
from sqlalchemy.orm import selectinload,joinedload
from core import db
from app.follows.models import Follow
from app.common.database import pagination_utils
from sqlalchemy.orm import aliased
from app.users.models import User



class FollowRepository:
    """关注关系仓储：封装关注/取关的数据访问。"""

    @staticmethod
    def get_relation(follower_id: int, followed_id: int,lock:bool=False) -> Optional[Follow]:
        """获取某个关注关系（唯一约束，未删除）。"""
        query = Follow.query.filter_by(follower_id=follower_id, followed_id=followed_id, is_deleted=False)
        if lock:
            query = query.with_for_update()
        return query.first()

    @staticmethod
    def create_follow(follower_id: int, followed_id: int) -> Follow:
        """创建关注关系（不提交事务，上层控制 commit/rollback）。"""
        follow = Follow(follower_id=follower_id, followed_id=followed_id)
        db.session.add(follow)
        return follow

    @staticmethod
    def delete_follow(follow: Follow) -> None:
        """删除关注关系（软删除），不提交事务。"""
        follow.is_deleted = True
        db.session.add(follow)

    @staticmethod
    def list_following(user_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """分页获取我关注的人（未删除）。"""
        query = (
            Follow.query.options(selectinload(Follow.followed))
            .filter_by(follower_id=user_id, is_deleted=False)
            .order_by(Follow.id.desc())
        )
        result=pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }

    @staticmethod
    def list_followers(user_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """分页获取关注我的人（未删除）。"""
        query = (
            Follow.query.options(selectinload(Follow.follower))
            .filter_by(followed_id=user_id, is_deleted=False)
            .order_by(Follow.id.desc())
        )
        result=pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }
    @staticmethod
    def get_mutual_follows(user_id: int, page: int = 1, per_page: int = 20):
        """
        获取互相关注的用户列表（未删除的关注关系）
        条件：A 关注 user_id 且 user_id 关注 A
        """
        F1 = aliased(Follow)  # A -> user_id
        F2 = aliased(Follow)  # user_id -> A
        
        query = (
            User.query
            .join(F1, User.id == F1.follower_id)
            .join(F2, User.id == F2.followed_id)
            .filter(F1.followed_id == user_id)
            .filter(F1.is_deleted == False)  # 未删除
            .filter(F2.follower_id == user_id)
            .filter(F2.is_deleted == False)  # 未删除
            .filter(User.is_active == True)
            .filter(User.is_deleted == False)  # 用户也未删除
            .order_by(F1.created_at.desc())
            .distinct()
        )
        
        return pagination_utils.paginate(query, page=page, per_page=per_page)
    


follow_repository = FollowRepository()