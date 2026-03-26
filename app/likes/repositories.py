from typing import Optional, Dict, Any
from sqlalchemy.orm import selectinload,joinedload
from core import db
from app.likes.models import Like
from app.common.database import pagination_utils


class LikeRepository:
    """点赞仓储：封装帖子/评论点赞的数据库访问。"""
    @staticmethod
    def get_by_id(like_id:int):
        return Like.query.filter_by(id=like_id, is_deleted=False).first() 
    @staticmethod
    def get_post_like(user_id: int, post_id: int) -> Optional[Like]:
        return Like.query.options(joinedload(Like.user)).filter_by(user_id=user_id, post_id=post_id, is_deleted=False).first()

    @staticmethod
    def get_comment_like(user_id: int, comment_id: int) -> Optional[Like]:
        return Like.query.options(joinedload(Like.user)).filter_by(user_id=user_id, comment_id=comment_id, is_deleted=False).first()
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
        """软删除点赞"""
        like.is_deleted = True
        db.session.add(like)

    @staticmethod
    def list_post_likes(post_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """分页获取某帖子下的点赞列表（排除已删除）。"""
        query = (
            Like.query.options(selectinload(Like.user))
            .filter_by(post_id=post_id, is_deleted=False)
            .order_by(Like.id.desc())
        )
        result=pagination_utils.paginate(query, page=page, per_page=per_page)
        return{
            'items':result['items'],
            'pagination':result['pagination']
        }

    

    @staticmethod
    def list_comment_likes(comment_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """分页获取某评论下的点赞列表（排除已删除）。"""
        query = (
            Like.query.options(selectinload(Like.user))
            .filter_by(comment_id=comment_id, is_deleted=False)
            .order_by(Like.id.desc())
        )
        result= pagination_utils.paginate(query, page=page, per_page=per_page)
        return{
            'items':result['items'],
            'pagination':result['pagination']
        }

    @staticmethod
    def list_by_user(user_id:int,page:int=1,per_page:int=20):
        """获取用户的点赞列表（排除已删除）。"""
        query=Like.query.filter_by(user_id=user_id, is_deleted=False).order_by(Like.created_at.desc())
        result= pagination_utils.paginate(query, page=page, per_page=per_page)
        return{
            'items':result['items'],
            'pagination':result['pagination']
        }
    
    @staticmethod
    def exists( user_id: int, post_id: int) -> bool:
        """检查是否已点赞（未删除的）"""
        return db.session.query(
            Like.query.filter_by(
                user_id=user_id, 
                post_id=post_id,
                is_deleted=False
            ).exists()
        ).scalar()

    @staticmethod
    def get_liked_post_ids( user_id: int, post_ids) -> set:
        """
        批量获取用户点赞的帖子ID集合（排除已删除）
        用于优化 has_liked 查询（避免 N+1）
        """
        if not post_ids:
            return set()
        
        liked = Like.query.filter(
            Like.user_id == user_id,
            Like.post_id.in_(post_ids),
            Like.is_deleted == False
        ).all()
        
        return {l.post_id for l in liked}

like_repository = LikeRepository()
