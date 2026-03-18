from typing import Optional, Dict, Any
from sqlalchemy.orm import selectinload,joinedload
from core import db
from app.likes.models import Like
from app.common.database import pagination_utils


class LikeRepository:
    """点赞仓储：封装帖子/评论点赞的数据库访问。"""
    @staticmethod
    def get_by_id(like_id:int):
        return Like.query.get(like_id) 
    @staticmethod
    def get_post_like(user_id: int, post_id: int) -> Optional[Like]:
        return Like.query.options(joinedload(Like.user)).filter_by(user_id=user_id, post_id=post_id).first()

    @staticmethod
    def get_comment_like(user_id: int, comment_id: int) -> Optional[Like]:
        return Like.query.options(joinedload(Like.user)).filter_by(user_id=user_id, comment_id=comment_id).first()
    @staticmethod
    def create_post_like(user_id: int, post_id: int) -> Like:
        like = Like(user_id=user_id, post_id=post_id)
        db.session.add(like)
        return like

    @staticmethod
    def create_comment_like(user_id: int, comment_id: int) -> Like:
        like = Like(user_id=user_id, comment_id=comment_id)
        db.session.add(like)
        return like

    @staticmethod
    def delete_like(like: Like) -> None:
        db.session.delete(like)

    @staticmethod
    def list_post_likes(post_id: int, page: int = 1, size: int = 20) -> Dict[str, Any]:
        """分页获取某帖子下的点赞列表。"""
        query = (
            Like.query.options(selectinload(Like.user))
            .filter_by(post_id=post_id)
            .order_by(Like.id.desc())
        )
        return pagination_utils.paginate(query, page=page, per_page=size)

    @staticmethod
    def list_comment_likes(comment_id: int, page: int = 1, size: int = 20) -> Dict[str, Any]:
        """分页获取某评论下的点赞列表。"""
        query = (
            Like.query.options(selectinload(Like.user))
            .filter_by(comment_id=comment_id)
            .order_by(Like.id.desc())
        )
        return pagination_utils.paginate(query, page=page, per_page=size)

    @staticmethod
    def list_by_user(user_id:int,page:int=1,size:int=20):
        query=Like.query.filter_by(user_id=user_id).order_by(Like.created_at.desc())
        return pagination_utils.paginate(query,page=page,per_page=size)

like_repository = LikeRepository()
