from typing import Optional, Dict, Any
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import selectinload

from core import db
from app.posts.models import Post
from app.common.database import pagination_utils


class PostRepository:
    @staticmethod
    def get_by_id(post_id: int) -> Optional[Post]:
        return Post.query.options(
            joinedload(Post.author)  # 只预加载作者
        ).filter_by(id=post_id, is_deleted=False).first()

    @staticmethod
    def create_post(user_id: int, content: str, image_url: str = None) -> Post:
        post = Post(content=content, image_url=image_url, user_id=user_id)
        db.session.add(post)
        return post

    @staticmethod
    def list_posts(page: int = 1, per_page: int = 20, user_id: Optional[int] = None):
        query = Post.query.options(joinedload(Post.author)).filter_by(is_published=True, is_deleted=False)
        if user_id:
            query = query.filter_by(user_id=user_id)
        return pagination_utils.paginate(query.order_by(Post.created_at.desc()), page=page, per_page=per_page)

    @staticmethod
    def search_posts(query_str: str, page: int = 1, per_page: int = 20):
        return pagination_utils.paginate(
            Post.query.options(joinedload(Post.author))
            .filter(Post.is_published == True, Post.is_deleted == False, Post.content.ilike(f"%{query_str}%"))
            .order_by(Post.created_at.desc()),
            page=page,
            per_page=per_page,
        )

    @staticmethod
    def soft_delete_post(post: Post) -> None:
        post.is_deleted = True
        for comment in post.comments.all():
            comment.is_deleted = True
        for like in post.likes.all():
            like.is_deleted = True
        db.session.add(post)


post_repository = PostRepository()
