from typing import Any

from sqlalchemy.orm import joinedload, selectinload

from app.common.database import get_read_session, pagination_utils
from app.common.exceptions import ConflictError
from app.likes.models import Like
from core import db
from core.metrics import monitor_db


class LikeRepository:
    """点赞仓储：封装帖子/评论点赞的数据库访问。"""

    @staticmethod
    def _read_session():
        return get_read_session()

    @staticmethod
    def _get_session(force_master: bool = False):
        return db.session if force_master else LikeRepository._read_session()

    @staticmethod
    @monitor_db("select","likes")
    def get_by_id(like_id: int, force_master: bool = False) -> Like | None:
        session = LikeRepository._get_session(force_master)
        return session.query(Like).filter(
            Like.id == like_id,
            Like.deleted_at.is_(None)
        ).first()

    @staticmethod
    @monitor_db("select","likes")
    def get_post_like(user_id: int, post_id: int, force_master: bool = False) -> Like | None:
        session = LikeRepository._get_session(force_master)
        return session.query(Like).options(
            joinedload(Like.user)
        ).filter(
            Like.user_id == user_id,
            Like.post_id == post_id,
            Like.deleted_at.is_(None)
        ).first()

    @staticmethod
    @monitor_db("select","likes")
    def get_comment_like(user_id: int, comment_id: int, force_master: bool = False) -> Like | None:
        session = LikeRepository._get_session(force_master)
        return session.query(Like).options(
            joinedload(Like.user)
        ).filter(
            Like.user_id == user_id,
            Like.comment_id == comment_id,
            Like.deleted_at.is_(None)
        ).first()

    @staticmethod
    @monitor_db("insert","likes")
    def create_post_like(user_id: int, post_id: int) -> Like:
        existing = db.session.query(Like).filter(
            Like.user_id == user_id,
            Like.post_id == post_id,
            Like.deleted_at.is_(None)
        ).first()
        if existing:
            raise ConflictError('点赞记录已存在')
        like = Like(user_id=user_id, post_id=post_id)
        db.session.add(like)
        return like

    @staticmethod
    @monitor_db("insert","likes")
    def create_comment_like(user_id: int, comment_id: int) -> Like:
        existing = db.session.query(Like).filter(
            Like.user_id == user_id,
            Like.comment_id == comment_id,
            Like.deleted_at.is_(None)
        ).first()
        if existing:
            raise ConflictError('点赞记录已存在')
        like = Like(user_id=user_id, comment_id=comment_id)
        db.session.add(like)
        return like

    @staticmethod
    @monitor_db("delete","likes")
    def delete_like(like: Like) -> None:
        """硬删除点赞（取消点赞是低频动作，硬删让 active 唯一约束生效）"""
        db.session.delete(like)

    @staticmethod
    @monitor_db("select","likes")
    def list_post_likes(post_id: int, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        """分页获取某帖子下的点赞列表（排除已删除）。"""
        session = LikeRepository._read_session()
        query = session.query(Like).options(
            selectinload(Like.user)
        ).filter(
            Like.post_id == post_id,
            Like.deleted_at.is_(None)
        ).order_by(Like.id.desc())
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }

    @staticmethod
    @monitor_db("select","likes")
    def list_comment_likes(comment_id: int, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        """分页获取某评论下的点赞列表（排除已删除）。"""
        session = LikeRepository._read_session()
        query = session.query(Like).options(
            selectinload(Like.user)
        ).filter(
            Like.comment_id == comment_id,
            Like.deleted_at.is_(None)
        ).order_by(Like.id.desc())
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }

    @staticmethod
    @monitor_db("select","likes")
    def list_by_user(user_id: int, page: int = 1, per_page: int = 20):
        """获取用户的点赞列表（排除已删除）。"""
        session = LikeRepository._read_session()
        query = session.query(Like).filter(
            Like.user_id == user_id,
            Like.deleted_at.is_(None)
        ).order_by(Like.created_at.desc())
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }

    @staticmethod
    @monitor_db("select","likes")
    def exists(user_id: int, post_id: int) -> bool:
        """检查是否已点赞（未删除的）"""
        session = LikeRepository._read_session()
        return session.query(
            session.query(Like).filter(
                Like.user_id == user_id,
                Like.post_id == post_id,
                Like.deleted_at.is_(None)
            ).exists()
        ).scalar()

    @staticmethod
    @monitor_db("select","likes")
    def get_liked_post_ids(user_id: int, post_ids) -> set:
        """
        批量获取用户点赞的帖子ID集合（排除已删除）
        用于优化 has_liked 查询（避免 N+1）
        """
        if not post_ids:
            return set()
        session = LikeRepository._read_session()
        liked = session.query(Like).filter(
            Like.user_id == user_id,
            Like.post_id.in_(post_ids),
            Like.deleted_at.is_(None)
        ).all()
        return {like.post_id for like in liked}

    @staticmethod
    @monitor_db("count","likes")
    def count_likes_for_post(post_id, force_master: bool = False):
        """帖子有效点赞数（DB层，对账/冷启动初始化用）"""
        session = LikeRepository._get_session(force_master)
        return session.query(Like).filter(
            Like.post_id == post_id,
            Like.deleted_at.is_(None)
        ).count()

    @staticmethod
    @monitor_db("count","likes")
    def count_likes_for_comment(comment_id, force_master: bool = False):
        """评论有效点赞数（DB层，对账/冷启动初始化用）"""
        session = LikeRepository._get_session(force_master)
        return session.query(Like).filter(
            Like.comment_id == comment_id,
            Like.deleted_at.is_(None)
        ).count()

like_repository = LikeRepository()
