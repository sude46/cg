from typing import Optional, Dict, Any
from sqlalchemy.orm import selectinload,joinedload
from core import db
from app.comments.models import Comment
from app.common.database import pagination_utils


class CommentRepository:
    """评论仓储：封装 Comment 相关的数据访问逻辑。"""

    @staticmethod
    def get_by_id(comment_id: int) -> Optional[Comment]:
        """根据 ID 获取评论（包含已删除）。"""
        return Comment.query.options(joinedload(Comment.author)).filter_by(id=comment_id).first()

    @staticmethod
    def get_active_by_id(comment_id: int) -> Optional[Comment]:
        """根据 ID 获取未删除的评论。"""
        return Comment.query.options(joinedload(Comment.author)).filter_by(id=comment_id, is_deleted=False).first()

    @staticmethod
    def create_comment(post_id: int, user_id: int, content: str) -> Comment:
        """创建评论，不提交事务（由上层 service 控制提交/回滚）。"""
        comment = Comment(post_id=post_id, user_id=user_id, content=content)
        db.session.add(comment)
        return comment 
    
    @staticmethod
    def list_by_post(post_id: int, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """按帖子分页查询评论列表（只返回未删除评论）。"""
        query=Comment.query.options(
            joinedload(Comment.author)
            ).filter_by(
            post_id=post_id,
            is_deleted=False
        ).order_by(Comment.created_at.desc())
        result=pagination_utils.paginate(query,page=page,per_page=per_page)
        return {
            'items':result['items'],
            'pagination':result['pagination']
        }
         
    @staticmethod
    def soft_delete(comment: Comment) -> None:
        """软删除评论（标记 is_deleted=True），不提交事务。"""
        comment.is_deleted = True
        db.session.add(comment)

    @staticmethod
    def increment_like_count(comment_id: int) -> None:
        """原子操作：增加评论点赞计数"""
        Comment.query.filter_by(id=comment_id).update({
            'like_count': Comment.like_count + 1
        })

    @staticmethod
    def decrement_like_count(comment_id: int) -> None:
        """原子操作：减少评论点赞计数（不小于0）"""
        from sqlalchemy import case
        Comment.query.filter_by(id=comment_id).update({
            'like_count': case((Comment.like_count > 0, Comment.like_count - 1), else_=0)
        })


comment_repository = CommentRepository()