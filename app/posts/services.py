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
    ConflictError
)
from app.common import event_bus
from typing import Dict, Any, List, Optional
from app.posts.repositories import post_repository
from  services.search import PostSearchService
import logging
from sqlalchemy.orm.exc import StaleDataError

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
        
        try:
            event_bus.publish('post.created',{
                
                    'id':post.id,
                    'content':post.content,
                    'user_id':post.user_id,
                    'user_name':user.username,
                    'image_url':post.image_url,
                    'like_count':post.like_count,
                    'comment_count':post.comment_count,
                    'created_at':post.created_at.isoformat(),
                    'is_published':post.is_published,
                    'is_deleted':post.is_deleted
            })
        except Exception as e:
            logger.warning(f'ES 索引失败（不影响主流程）: {e}')
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
    def update_post(post_id: int, user_id: int, content: str = None, image_url: str = None
    ) -> Post:
        """更新帖子，返回更新后的 Post ORM 对象"""
        try:

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
            try:
                event_bus.publish('post.update',{
                    'post_id':post_id,
                    'content':post.content,
                    'image_url':post.image_url
                })
            except Exception as e:
                logging.warning('发布帖子更新事件失败，不影响主进程：{e}')
            logger.info('用户%d更新了帖子%d', user_id, post_id)
            return post
        except StaleDataError:
            db.session.rollback()
            logger.warning(f'贴子{post_id}更新冲突')
            raise ConflictError('该帖子已被其他用户修改，请刷新后重试')


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
        
        # 同步删除 ES 索引
        try:
            event_bus.publish('post.deleted',{'post_id':post_id})
        except Exception as e:
            logger.warning(f'发布帖子删除事件失败（不影响主流程）: {e}')
        
        logger.info('用户%d软删除了帖子%d', user_id, post_id)

    # ========== 搜索 ==========
    @staticmethod
    def search_posts(
        query: str, 
        page: int = 1, 
        per_page: int = 20, 
        current_user_id: int = None,
        sort_by: str = 'relevance'
    ) -> Dict[str, Any]:
        """
        搜索帖子（使用 Elasticsearch）
        
        Args:
            query: 搜索关键词
            page: 页码
            per_page: 每页数量
            current_user_id: 当前用户ID（用于获取点赞状态）
            sort_by: 排序方式：relevance(相关度)、time(时间)、hot(热度)
        """
        per_page = min(100, max(1, per_page))
        page = max(1, page)

        # 使用 ES 搜索
        result = PostSearchService.search(
            query=query,
            page=page,
            per_page=per_page,
            sort_by=sort_by,
            current_user_id=current_user_id
        )
        
        posts = result.get('items', [])
        
        # 获取点赞状态（如果 ES 返回的是 ID 列表）
        liked_ids = set()
        if current_user_id and posts and not result.get('fallback'):
            # ES 搜索结果需要从数据库查点赞状态
            post_ids = [p['id'] for p in posts]
            liked_ids = like_repository.get_liked_post_ids(
                user_id=current_user_id,
                post_ids=post_ids
            )
        elif current_user_id and posts:
            # 降级到数据库搜索时
            liked_ids = like_repository.get_liked_post_ids(
                user_id=current_user_id,
                post_ids=[p['id'] for p in posts]
            )

        return {
            'items': posts,
            'pagination': result.get('pagination', {}),
            'liked_post_ids': liked_ids,
            'is_es_search': not result.get('fallback', False)
        }