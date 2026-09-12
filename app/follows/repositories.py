from typing import Any

from sqlalchemy.orm import aliased, selectinload

from app.common.database import get_read_session, pagination_utils, utcnow
from app.follows.models import Follow
from app.users.models import User
from core import db
from core.metrics import monitor_db


class FollowRepository:
    """关注关系仓储：封装关注/取关的数据访问。"""

    @staticmethod
    def _read_session():
        return get_read_session()


    @staticmethod
    @monitor_db("select", "follows")
    def get_relation(follower_id: int, followed_id: int,lock:bool=False) -> Follow | None:
        """
        获取某个关注关系（唯一约束，未删除）。
        lock=True:走主库+select for update（写操作钱校验）
        lock=False:走从库
        """
        if lock:
            query=db.session.query(Follow).with_for_update()
        else:
            query=FollowRepository._read_session().query(Follow)
        return query.filter(
            Follow.follower_id==follower_id,
            Follow.followed_id==followed_id,
            Follow.deleted_at.is_(None)
        ).first()

    @staticmethod
    @monitor_db("select", "follows")
    def get_follower_ids(followed_id:int):
        '''
        获取粉丝ID列表（Feed推送用）
        走从库，O(N)查全表，大V用户可能慢，上层建议走FollowCache
        '''
        session=FollowRepository._read_session()
        rows=session.query(Follow.follower_id).filter(
            Follow.followed_id==followed_id,
            Follow.deleted_at.is_(None)
        ).all()
        return [r[0] for r in rows]


    @staticmethod
    @monitor_db("insert", "follows")
    def create_follow(follower_id: int, followed_id: int) -> Follow:
        """创建关注关系（不提交事务，上层控制 commit/rollback）。"""
        follow = Follow(follower_id=follower_id, followed_id=followed_id)
        db.session.add(follow)
        return follow

    @staticmethod
    @monitor_db("update", "follows")
    def delete_follow(follow: Follow) -> None:
        """删除关注关系（软删除），不提交事务。"""
        follow.deleted_at=utcnow()
        db.session.add(follow)

    @staticmethod
    @monitor_db("select", "follows")
    def list_following(user_id: int, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        """分页获取我关注的人。"""
        session=FollowRepository._read_session()
        query = session.query(Follow).options(
            selectinload(Follow.followed)
            ).filter(
            Follow.follower_id==user_id,
            Follow.deleted_at.is_(None)
            ).order_by(Follow.id.desc())

        result=pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }

    @staticmethod
    @monitor_db("select", "follows")
    def list_followers(user_id: int, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        """分页获取关注我的人"""
        session=FollowRepository._read_session()
        query = (
            session.query(Follow).options(selectinload(Follow.follower))
            .filter(Follow.followed_id==user_id,Follow.deleted_at.is_(None))
            .order_by(Follow.id.desc())
        )
        result=pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }
    @staticmethod
    @monitor_db("select", "follows")
    def get_mutual_follows(user_id: int, page: int = 1, per_page: int = 20):
        """
        获取互相关注的用户列表（未删除的关注关系）
        条件：A 关注 user_id 且 user_id 关注 A
        """
        F1 = aliased(Follow)  # A -> user_id
        F2 = aliased(Follow)  # user_id -> A

        session=FollowRepository._read_session()

        query = session.query(User).join(
            F1, User.id == F1.follower_id
        ).join(
            F2, User.id == F2.followed_id
        ).filter(
            F1.followed_id == user_id,
            F1.deleted_at.is_(None),
            F2.follower_id == user_id,
            F2.deleted_at.is_(None)
        ).order_by(F1.created_at.desc()).distinct()


        return pagination_utils.paginate(query, page=page, per_page=per_page)



follow_repository = FollowRepository()
