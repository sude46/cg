from typing import Optional, Dict, Any
from sqlalchemy.orm import joinedload
from core import db
from app.comments.models import Comment
from app.common.database import pagination_utils, get_read_session
from sqlalchemy import case, update
from datetime import datetime,timezone
from app.common.database import utcnow
from core.metrics import monitor_db



class CommentRepository:
    """评论仓储：封装 Comment 相关的数据访问逻辑。"""
    @staticmethod
    def _read_session():
        return get_read_session()
    

    @staticmethod
    @monitor_db("select", "comments")
    def get_by_id(comment_id: int,force_master:bool=False) -> Optional[Comment]:
        """根据 ID 获取评论（包含已删除）。"""
        session=db.session if force_master else CommentRepository._read_session()

        return session.query(Comment).options(
            joinedload(Comment.author)).filter(
                Comment.id==comment_id,Comment.deleted_at.is_(None)
                ).first()

    @staticmethod
    @monitor_db("select", "comments")
    def get_active_by_id(comment_id: int) -> Optional[Comment]:
        """根据 ID 获取未删除的评论。"""
        return Comment.query.options(joinedload(Comment.author)).filter_by(id=comment_id).filter(Comment.deleted_at.is_(None)).first()

    @staticmethod
    @monitor_db("insert", "comments")
    def create_comment(post_id: int, user_id: int, content: str) -> Comment:
        """创建评论，不提交事务（由上层 service 控制提交/回滚）。"""

        comment = Comment(post_id=post_id, user_id=user_id, content=content)
        db.session.add(comment)
        return comment 
    
    @staticmethod
    @monitor_db("select", "comments")
    def list_by_post(post_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """按帖子分页查询评论列表（只返回未删除评论）。"""
        session=CommentRepository._read_session()
        query=session.query(Comment).options(
            joinedload(Comment.author)
            ).filter(
            Comment.post_id==post_id,
            Comment.deleted_at.is_(None)
        ).order_by(Comment.created_at.desc())
        result=pagination_utils.paginate(query,page=page,per_page=per_page)
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }
         
    @staticmethod
    @monitor_db("update", "comments")
    def soft_delete(comment: Comment) -> None:
        """软删除评论（设置 deleted_at），不提交事务。"""
        comment.deleted_at=utcnow()

    @staticmethod
    @monitor_db("select", "comments")
    def list_top_by_likes(post_id: int, limit: int = 100):
        """按点赞数倒序获取帖子的热门评论（对账重建用）"""
        session = CommentRepository._read_session()
        return session.query(Comment).filter(
            Comment.post_id == post_id,
            Comment.deleted_at.is_(None)
        ).order_by(Comment.like_count.desc()).limit(limit).all()

    @staticmethod
    @monitor_db("update", "comments")
    def increment_like_count(comment_id: int) -> None:
        """原子递增：SET like_count = like_count + 1"""
        db.session.execute(
            update(Comment)
            .where(Comment.id == comment_id)
            .values(like_count=Comment.like_count + 1)
        )

    @staticmethod
    @monitor_db("update", "comments")
    def decrement_like_count(comment_id: int) -> None:
        """原子递减（不低于0）"""
        db.session.execute(
            update(Comment)
            .where(Comment.id == comment_id)
            .values(like_count=case((Comment.like_count > 0, Comment.like_count - 1), else_=0))
        )

    @staticmethod
    @monitor_db("update", "comments")
    def update_like_count(comment_id: int, count: int) -> None:
        """直接更新评论点赞计数（对账修正用，强制不小于0）"""
        db.session.execute(
            update(Comment)
            .where(Comment.id == comment_id)
            .values(like_count=max(0, count))
        )
        # 注意：不 commit — 事务由调用方（Service / Task）统一管理


comment_repository = CommentRepository()
