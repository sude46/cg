
from sqlalchemy import case, update
from sqlalchemy.orm import joinedload

from app.common.database import get_read_session, pagination_utils, utcnow
from app.posts.models import Post
from core import db
from core.metrics import monitor_db


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
    ) -> Post | None:
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
        user_id: int | None = None
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
    def _escape_like(value: str) -> str:
        """转义 LIKE 通配符：顺序必须是先反斜杠、再 % 和 _"""
        return (value or '').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

    @staticmethod
    @monitor_db("select", "posts")
    def search_posts(query_str: str, page: int = 1, per_page: int = 20):
        session = PostRepository._read_session()
        escaped = PostRepository._escape_like(query_str)
        query = session.query(Post).options(
            joinedload(Post.author)
        ).filter(
            Post.deleted_at.is_(None),
            Post.is_published.is_(True),
            Post.content.ilike(f'%{escaped}%', escape='\\')
        ).order_by(Post.created_at.desc())
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }

    @staticmethod
    @monitor_db("select", "posts")
    def search_post_ids(query_str: str, page: int = 1, per_page: int = 20):
        """降级搜索：只取 ID + 总数，便于短 TTL 缓存，避免重复全表 LIKE"""
        session = PostRepository._read_session()
        escaped = PostRepository._escape_like(query_str)
        query = session.query(Post.id).filter(
            Post.deleted_at.is_(None),
            Post.is_published.is_(True),
            Post.content.ilike(f'%{escaped}%', escape='\\')
        ).order_by(Post.created_at.desc())
        total = query.count()
        rows = query.limit(per_page).offset((page - 1) * per_page).all()
        return [row[0] for row in rows], total

    @staticmethod
    @monitor_db("select", "posts")
    def get_by_ids(post_ids):
        """按 ID 批量取帖子（含作者），保持传入顺序并过滤已删除"""
        if not post_ids:
            return []
        session = PostRepository._read_session()
        rows = session.query(Post).options(
            joinedload(Post.author)
        ).filter(
            Post.id.in_(post_ids),
            Post.deleted_at.is_(None)
        ).all()
        by_id = {p.id: p for p in rows}
        return [by_id[i] for i in post_ids if i in by_id]

    @staticmethod
    @monitor_db("select", "posts")
    def get_posts_updated_since(since, limit: int = 5000):
        """取某时间点后被创建/更新/软删的帖子（含已删），用于 ES 降级恢复后补索引"""
        session = PostRepository._read_session()
        return session.query(Post).options(
            joinedload(Post.author)
        ).filter(
            Post.updated_at >= since
        ).order_by(Post.updated_at.asc()).limit(limit).all()

    @staticmethod
    @monitor_db("select", "posts")
    def list_posts_for_reindex(offset: int = 0, limit: int = 100):
        """按 id 顺序分页取未删除帖子（ES 全量重建索引用）"""
        session = PostRepository._read_session()
        return session.query(Post).options(
            joinedload(Post.author)
        ).filter(
            Post.deleted_at.is_(None)
        ).order_by(Post.id.asc()).limit(limit).offset(offset).all()

    @staticmethod
    @monitor_db("update", "posts")
    def soft_delete_post(post: Post) -> None:
        """软删除帖子及相关评论"""
        now = utcnow()
        post.deleted_at = now

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

