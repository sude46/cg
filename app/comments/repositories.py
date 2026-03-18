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
        return db.session.query(Comment).options(joinedload(Comment.author)).filter_by(id=comment_id).first()

    @staticmethod
    def get_active_by_id(comment_id: int) -> Optional[Comment]:
        """根据 ID 获取未删除的评论。"""
        return Comment.query.options(joinedload(Comment.author)).filter_by(id=comment_id, is_deleted=False).first()

    @staticmethod
    def list_by_post(post_id: int, page: int = 1, size: int = 20) -> Dict[str, Any]:
        """按帖子分页查询评论列表（只返回未删除评论）。"""
        query = (
            Comment.query.options(joinedload(Comment.author))
            .filter_by(post_id=post_id, is_deleted=False)
            .order_by(Comment.created_at.asc())
        )
        return pagination_utils.paginate(query, page=page, per_page=size)

    @staticmethod
    def create_comment(post_id: int, user_id: int, content: str) -> Comment:
        """创建评论，不提交事务（由上层 service 控制提交/回滚）。"""
        comment = Comment(post_id=post_id, user_id=user_id, content=content)
        db.session.add(comment)
        return comment

    @staticmethod
    def soft_delete(comment: Comment) -> None:
        """软删除评论（标记 is_deleted=True），不提交事务。"""
        comment.is_deleted = True
        db.session.add(comment)


comment_repository = CommentRepository()