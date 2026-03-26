from core.database import db
from .models import Post
from .schemas import post_schema
from app.users.repositories import user_repository
from app.likes.repositories import like_repository
from app.common.exceptions import (
    ValidationError,
    ResourceNotFoundError,
    AuthenticationError,
    DatabaseError,
)
from typing import Dict, Any, List, Optional
from app.posts.repositories import post_repository
import logging

logger = logging.getLogger(__name__)


class PostService:
    '''帖子服务类'''

    # ========== 创建 ==========
    @staticmethod
    def create_post(user_id: int, content: str, image_url: str = None) -> Post:
        """创建帖子，返回 Post ORM 对象（不序列化）"""
        if not content or len(content.strip()) == 0:
            raise ValidationError('帖子内容不能为空')
        if len(content.strip()) > 1000:
            raise ValidationError('帖子内容不能超过1000个字符')

        user = user_repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError('用户')

        post = post_repository.create_post(
            user_id=user_id, 
            content=content.strip(), 
            image_url=image_url
        )
        db.session.commit()
        logger.info('用户%d创建了帖子%d', user_id, post.id)
        return post

    # ========== 查询 ==========
    @staticmethod
    def get_posts(
        page: int = 1, 
        per_page: int = 20, 
        user_id: int = None, 
        current_user_id: int = None
    ) -> Dict[str, Any]:
        """
        获取帖子列表
        返回: {'items': [Post, ...], 'pagination': {...}, 'liked_post_ids': set}
        """
        per_page = min(100, max(1, per_page))
        page = max(1, page)

        result = post_repository.list_posts(
            page=page, 
            per_page=per_page, 
            user_id=user_id
        )
        posts = result.get('items', [])
        
        # 通过 Repository 获取点赞状态，而不是直接查 Model
        liked_ids = set()
        if current_user_id and posts:
            liked_ids = like_repository.get_liked_post_ids(
                user_id=current_user_id,
                post_ids=[p.id for p in posts]
            )

        return {
            'items': posts,  # ORM 对象列表，不序列化
            'pagination': result.get('pagination', {}),
            'liked_post_ids': liked_ids  # 额外的点赞状态数据
        }

    @staticmethod
    def get_post(post_id: int, current_user_id: int = None) -> Dict[str, Any]:
        """
        获取单个帖子
        返回: {'post': Post, 'has_liked': bool}
        """
        post = post_repository.get_by_id(post_id)
        if not post or not post.is_published:
            raise ResourceNotFoundError('帖子')

        has_liked = False
        if current_user_id:
            has_liked = like_repository.exists(
                user_id=current_user_id, 
                post_id=post.id
            )

        return {'post': post, 'has_liked': has_liked}

    # ========== 更新 ==========
    @staticmethod
    def update_post(
        post_id: int, 
        user_id: int, 
        content: str = None, 
        image_url: str = None
    ) -> Post:
        """更新帖子，返回更新后的 Post ORM 对象"""
        post = post_repository.get_by_id(post_id)
        if not post:
            raise ResourceNotFoundError('帖子')
        if post.user_id != user_id:
            raise AuthenticationError('无权修改此帖子')
        if content is None and image_url is None:
            raise ValidationError('至少提供一个更新内容')

        if content is not None:
            if len(content.strip()) == 0:
                raise ValidationError('帖子内容不能为空')
            if len(content.strip()) > 1000:
                raise ValidationError('帖子内容不能超过1000个字符')
            post.content = content.strip()
        
        if image_url is not None:
            post.image_url = image_url

        db.session.commit()
        logger.info('用户%d更新了帖子%d', user_id, post_id)
        return post

    # ========== 删除 ==========
    @staticmethod
    def delete_post(post_id: int, user_id: int) -> None:
        """删除帖子，无返回值"""
        post = post_repository.get_by_id(post_id)
        if not post:
            raise ResourceNotFoundError('帖子')
        if post.user_id != user_id:
            raise AuthenticationError('无权删除该帖子')

        post_repository.soft_delete_post(post)
        db.session.commit()
        logger.info('用户%d软删除了帖子%d', user_id, post_id)

    # ========== 点赞相关 ==========
    @staticmethod
    def like_post(post_id: int, user_id: int) -> None:
        """点赞帖子"""
        post = post_repository.get_by_id(post_id)
        if not post or not post.is_published:
            raise ResourceNotFoundError('帖子')
        
        # 检查是否已点赞
        if like_repository.exists(user_id=user_id, post_id=post_id):
            raise ValidationError('已点赞该帖子')

        like_repository.create_post_like(user_id=user_id, post_id=post_id)
        post.like_count = (post.like_count or 0) + 1
        db.session.commit()
        logger.info('用户%d点赞了帖子%d', user_id, post_id)

    @staticmethod
    def unlike_post(post_id: int, user_id: int) -> None:
        """取消点赞"""
        like = like_repository.get_post_like(user_id=user_id, post_id=post_id)
        if not like:
            raise ResourceNotFoundError('点赞记录')

        like_repository.delete_like(like)
        post = post_repository.get_by_id(post_id)
        if post:
            post.like_count = max(0, (post.like_count or 0) - 1)
        db.session.commit()
        logger.info('用户%d取消点赞记录%d', user_id, post_id)

    # ========== 搜索 ==========
    @staticmethod
    def search_posts(
        query: str, 
        page: int = 1, 
        per_page: int = 20, 
        current_user_id: int = None
    ) -> Dict[str, Any]:
        """搜索帖子"""
        per_page = min(100, max(1, per_page))
        page = max(1, page)

        result = post_repository.search_posts(
            query, 
            page=page, 
            per_page=per_page
        )
        posts = result.get('items', [])
        
        # 获取点赞状态
        liked_ids = set()
        if current_user_id and posts:
            liked_ids = like_repository.get_liked_post_ids(
                user_id=current_user_id,
                post_ids=[p.id for p in posts]
            )

        return {
            'items': posts,
            'pagination': result.get('pagination', {}),
            'liked_post_ids': liked_ids
        }
