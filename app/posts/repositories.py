from core.metrics import monitor_db 
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from app.common.database import utcnow
from sqlalchemy.orm import joinedload
from core import db
from app.posts.models import Post
from app.common.database import pagination_utils, get_read_session
from sqlalchemy import case, update


class PostRepository:

    @staticmethod
    def _read_session():
        return get_read_session()

    @staticmethod
    @monitor_db("select", "posts")
    def get_by_id(
        post_id: int, 
        lock: bool = False, 
        force_master: bool = False
    ) -> Optional[Post]:
        """
        根据ID获取帖子
        - lock=True / force_master=True → 走主库
        - 否则 → 走从库
        """
        if lock or force_master:
            session = db.session
        else:
            session = PostRepository._read_session()

        query = session.query(Post).options(
            joinedload(Post.author)
        ).filter(
            Post.id == post_id,
            Post.deleted_at.is_(None)
        )
        
        if lock:
            query = query.with_for_update()
        return query.first()

    @staticmethod
    @monitor_db("insert", "posts")
    def create_post(user_id: int, content: str, image_url: str = None) -> Post:
        post = Post(
            content=content, 
            image_url=image_url, 
            user_id=user_id, 
            is_published=True
        )
        db.session.add(post)
        return post

    @staticmethod
    @monitor_db("select", "posts")
    def list_posts(
        page: int = 1, 
        per_page: int = 20, 
        user_id: Optional[int] = None
    ):
        session = PostRepository._read_session()
        query = session.query(Post).options(
            joinedload(Post.author)
        ).filter(
            Post.is_published.is_(True),
            Post.deleted_at.is_(None)
        )
        
        if user_id:
            query = query.filter_by(user_id=user_id)
        query = query.order_by(Post.created_at.desc())
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }

    @staticmethod
    @monitor_db("select", "posts")
    def search_posts(query_str: str, page: int = 1, per_page: int = 20):
        session = PostRepository._read_session()
        query = session.query(Post).options(
            joinedload(Post.author)
        ).filter(
            Post.deleted_at.is_(None),
            Post.is_published.is_(True),
            Post.content.ilike(f'%{query_str}%')
        ).order_by(Post.created_at.desc())
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }

    @staticmethod
    @monitor_db("update", "posts")
    def soft_delete_post(post: Post) -> None:
        """软删除帖子及相关评论"""
        now = utcnow()
        post.deleted_at = now
        
        # TODO: 确保 Comment 模型也有 deleted_at 字段，否则此处会报错
        for comment in post.comments.all():
            comment.deleted_at = now
        
        # Like 硬删除（无 deleted_at）
        for like in post.likes.all():
            db.session.delete(like)
        
        db.session.add(post)

    @staticmethod
    @monitor_db("update", "posts")
    def increment_like_count(post_id: int) -> None:
        """原子递增：SET like_count = like_count + 1，无客户端求值"""
        db.session.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(like_count=Post.like_count + 1)
        )

    @staticmethod
    @monitor_db("update", "posts")
    def decrement_like_count(post_id: int) -> None:
        """原子递减（不低于0）"""
        db.session.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(like_count=case((Post.like_count > 0, Post.like_count - 1), else_=0))
        )

    @staticmethod
    @monitor_db("update", "posts")
    def increment_comment_count(post_id: int) -> None:
        """原子递增：SET comment_count = comment_count + 1"""
        db.session.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(comment_count=Post.comment_count + 1)
        )

    @staticmethod
    @monitor_db("update", "posts")
    def decrement_comment_count(post_id: int) -> None:
        """原子递减（不低于0）"""
        db.session.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(comment_count=case((Post.comment_count > 0, Post.comment_count - 1), else_=0))
        )

    @staticmethod
    @monitor_db("update", "posts")
    def update_like_count(post_id: int, count: int) -> None:
        db.session.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(like_count=max(0, count))
        )
        # 注意：不 commit — 事务由调用方（Service / Task）统一管理


post_repository = PostRepository()

