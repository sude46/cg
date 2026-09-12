import logging
from typing import Any

from sqlalchemy.orm.exc import StaleDataError

from app.comments.cache import CommentCache
from app.common import event_bus
from app.common.database import utcnow
from app.common.exceptions import (
    AuthenticationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.likes.cache import LikeCache
from app.likes.repositories import like_repository
from app.posts.repositories import post_repository
from app.users.cache import UserCache
from app.users.repositories import user_repository
from core.database import db
from core.metrics import CELERY_TASKS, POST_OPERATIONS, REDIS_HIT_RATE
from services.search import PostSearchService

from .cache import PostCache
from .models import Post
from .schemas import post_schema

logger = logging.getLogger(__name__)


class PostService:
    '''帖子服务类'''

    # ========== 创建 (强一致：预热缓存+标记窗口)==========
    @staticmethod
    def create_post(user_id: int, content: str, image_url: str = None) -> Post:
        """创建帖子，返回 Post ORM 对象（不序列化）"""
        try:
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
            POST_OPERATIONS.labels(action='create', result='success').inc()

            #预热缓存
            post_dict=post_schema.dump(post)
            PostCache.set(post.id,post_dict)

            #强一致标记：5秒内必须走主库
            PostCache.mark_recently_modified(post.id,ttl=5)


            try:
                event_bus.publish('post.created',{

                        'id':post.id,
                        'content':post.content,
                        'user_id':post.user_id,
                        'user_name':user.username,
                        'image_url':post.image_url,
                        'like_count':post.like_count,
                        'comment_count':post.comment_count,
                        'created_at':post.created_at.isoformat() if post.created_at else None,
                        'is_published':post.is_published,
                        'deleted_at':post.deleted_at.isoformat() if post.deleted_at else None,
                })
            except Exception as e:
                logger.warning(f'ES 索引失败（不影响主流程）: {e}')
            POST_OPERATIONS.labels(action='create', result='success').inc()
            return post
        except Exception:
            POST_OPERATIONS.labels(action='create', result='error').inc()
            raise

    # ========== 查询 (强一致分支+弱一致Cache-Aside)==========
    @staticmethod
    def get_posts(
        page: int = 1,
        per_page: int = 20,
        user_id: int = None,
        current_user_id: int = None
    ) -> dict[str, Any]:
        """
        获取帖子列表（不走缓存，查从库）
        批量补充实时点赞数
        """
        try:
            per_page = min(100, max(1, per_page))
            page = max(1, page)

            result = post_repository.list_posts(
                page=page,
                per_page=per_page,
                user_id=user_id
            )
            posts = result.get('items', [])

            if posts:
                # 批量预热帖子作者的用户资料缓存
                author_ids = list(set(p.user_id for p in posts if hasattr(p, 'user_id')))
                if author_ids:
                    UserCache.preload_profiles(author_ids)

                # 批量补充点赞数（从 likes 缓存读）
                for post in posts:
                    redis_likes_count = LikeCache.get_like_count(post.id, 'post')
                    if redis_likes_count is not None:
                        post.like_count = redis_likes_count
                    redis_comments_count=CommentCache.get_count(post.id)
                    if redis_comments_count is not None:
                        post.comment_count=redis_comments_count

            # 批量查点赞状态
            liked_ids = set()
            if current_user_id and posts:
                liked_ids = like_repository.get_liked_post_ids(
                    user_id=current_user_id,
                    post_ids=[p.id for p in posts]
                )
                # 预热用户点赞状态到 Redis，后续 is_liked 直接命中缓存
                if liked_ids:
                    LikeCache.preload_user_likes(current_user_id, list(liked_ids))
            POST_OPERATIONS.labels(action='list', result='success').inc()
            return {
                'items': posts,  # ORM 对象列表，不序列化
                'pagination': result.get('pagination', {}),
                'liked_post_ids': liked_ids  # 额外的点赞状态数据
            }
        except Exception:
            POST_OPERATIONS.labels(action='list', result='error').inc()
            raise

    @staticmethod
    def get_post(post_id: int, current_user_id: int = None) -> dict[str, Any]:
        """
         获取单个帖子
        - 强一致：帖子最近被修改过 → 跳过缓存，直接查主库
        - 弱一致：Cache-Aside（缓存 → miss 查从库 → 回填主库）
        - 点赞数实时覆盖（调 likes 模块）
        """
        try:
            post_dict=None
            #判断是否需要强一致(RecentActivity标记)
            if PostCache.is_recently_modified(post_id):
                #强一致路径：跳过缓存，直接查主库
                post_obj=post_repository.get_by_id(post_id,force_master=True)
                if not post_obj or post_obj.deleted_at:
                    raise ResourceNotFoundError('帖子')
                post_dict=post_schema.dump(post_obj)
                #回填缓存
                PostCache.set(post_id,post_dict)
                REDIS_HIT_RATE.labels(cache_type='post').set(0)
            else:
                #弱一致路径:Cache-Aside
                cached=PostCache.get(post_id)
                if cached:
                    post_dict=cached
                    REDIS_HIT_RATE.labels(cache_type='post').set(1)
                else:
                    post_obj=post_repository.get_by_id(post_id,force_master=False)
                    if not post_obj or post_obj.deleted_at:
                        raise ResourceNotFoundError('帖子')
                    post_dict=post_schema.dump(post_obj)
                    PostCache.set(post_id,post_dict)
                    REDIS_HIT_RATE.labels(cache_type='post').set(0)
            # 2. 实时覆盖点赞数（likes 模块 O(1)）
            like_count = LikeCache.get_like_count(post_id, 'post')
            if like_count is not None:
                post_dict['like_count'] = like_count
            # 3. 实时覆盖评论数（TODO: 接入 comments/cache.py）
            comment_count = CommentCache.get_count(post_id)
            if comment_count is not None:
                post_dict['comment_count'] = comment_count

            # 4. 查询当前用户是否点赞
            has_liked = False
            if current_user_id:
                has_liked = LikeCache.is_liked(current_user_id, post_id, 'post') or False
            POST_OPERATIONS.labels(action='get', result='success').inc()
            return {'post': post_dict, 'has_liked': has_liked}
        except Exception:
            POST_OPERATIONS.labels(action='get', result='error').inc()
            raise




    # ========== 更新(延迟双删+强一致标记) ==========
    @staticmethod
    def update_post(post_id: int, user_id: int, content: str = None, image_url: str = None
    ) -> Post:
        """更新帖子，返回更新后的 Post ORM 对象"""
        try:
            # 权限校验必须走主库（确保读到最新）
            post = post_repository.get_by_id(post_id,force_master=True)
            if not post or post.deleted_at:
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

            #延迟双删---第一次删除+强一致标记
            PostCache.invalidate(post_id)
            PostCache.mark_recently_modified(post_id,ttl=5)

            #延迟双删---第二次删除（celery延迟任务，失败降级线程）
            try:
                from core.celery_app import celery_app
                celery_app.send_task(
                    'tasks.post_tasks.delayed_invalidate',
                    args=(post_id,),
                    countdown=2
                )
                CELERY_TASKS.labels(task_name='delayed_invalidate', status='published').inc()
            except Exception as e:
                CELERY_TASKS.labels(task_name='delayed_invalidate', status='publish_failed').inc()
                logger.warning(f'调度延迟删除失败，降级为线程:{e}')
                PostCache.double_invalidate(post_id)

            try:
                event_bus.publish('post.updated',{
                    'post_id':post_id,
                    'content':post.content,
                    'image_url':post.image_url,
                    'deleted_at': post.deleted_at.isoformat() if post.deleted_at else None,
                })
            except Exception:
                logging.warning('发布帖子更新事件失败，不影响主进程：{e}')
            POST_OPERATIONS.labels(action='update', result='success').inc()
            logger.info('用户%d更新了帖子%d', user_id, post_id)
            return post
        except StaleDataError:
            db.session.rollback()
            logger.warning(f'贴子{post_id}更新冲突')
            POST_OPERATIONS.labels(action='update', result='error').inc()
            raise ConflictError('该帖子已被其他用户修改，请刷新后重试')
        except Exception:
            POST_OPERATIONS.labels(action='update', result='error').inc()
            raise


    # ========== 删除(延迟双删+强一致标记) ==========
    @staticmethod
    def delete_post(post_id: int, user_id: int) -> None:
        """删除帖子，无返回值"""
        try:
            post = post_repository.get_by_id(post_id,force_master=True)
            if not post or post.deleted_at:
                raise ResourceNotFoundError('帖子')
            if post.user_id != user_id:
                raise AuthenticationError('无权删除该帖子')

            post_repository.soft_delete_post(post)
            db.session.commit()

            # 延迟双删
            PostCache.invalidate(post_id)
            PostCache.mark_recently_modified(post_id,ttl=5)
            try:
                from core.celery_app import celery_app
                celery_app.send_task(
                    'tasks.post_tasks.delayed_invalidate',
                    args=(post_id,),
                    countdown=2
                )
            except Exception as e:
                logger.warning(f'调度延迟删除失败，降级为线程: {e}')
                PostCache.double_invalidate(post_id)

            # 同步删除 ES 索引
            try:
                CELERY_TASKS.labels(task_name='delayed_invalidate', status='published').inc()
                event_bus.publish('post.deleted',{
                    'post_id':post_id,
                    'user_id':post.user_id,
                    'deleted_at': utcnow().isoformat(),
                    })
            except Exception as e:
                CELERY_TASKS.labels(task_name='delayed_invalidate', status='publish_failed').inc()
                logger.warning(f'发布帖子删除事件失败（不影响主流程）: {e}')

            POST_OPERATIONS.labels(action='delete', result='success').inc()
            logger.info('用户%d软删除了帖子%d', user_id, post_id)
        except Exception:
            POST_OPERATIONS.labels(action='delete', result='error').inc()
            raise


    # ========== 搜索 ==========
    @staticmethod
    def search_posts(
        query: str,
        page: int = 1,
        per_page: int = 20,
        current_user_id: int = None,
        sort_by: str = 'relevance'
    ) -> dict[str, Any]:
        """
        搜索帖子（使用 Elasticsearch）

        Args:
            query: 搜索关键词
            page: 页码
            per_page: 每页数量
            current_user_id: 当前用户ID（用于获取点赞状态）
            sort_by: 排序方式：relevance(相关度)、time(时间)、hot(热度)
        """
        try:
            per_page = min(100, max(1, per_page))
            page = max(1, page)

            # 使用 ES 搜索
            result = PostSearchService.search(
                query=query,
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                user_id=current_user_id
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
            POST_OPERATIONS.labels(action='search', result='success').inc()
            return {
                'items': posts,
                'pagination': result.get('pagination', {}),
                'liked_post_ids': liked_ids,
                'is_es_search': not result.get('fallback', False)
            }
        except Exception:
            POST_OPERATIONS.labels(action='search', result='error').inc()
            raise

    @staticmethod
    def get_hot_posts(page:int=1,per_page=20,period:str='daily'):
        try:
            post_ids,total=PostCache.get_hot_posts(page,per_page,period)

            #批量查帖子详情缓存
            posts=[]
            for pid in post_ids:
                post_dict=PostCache.get(pid)
                if post_dict:
                    #实时覆盖计数器
                    like_count=LikeCache.get_like_count(pid,'post')
                    if like_count is not None:
                        post_dict['like_count']=like_count
                    comment_count=CommentCache.get_count(pid)
                    if comment_count is not None:
                        post_dict['comment_count']=comment_count
                    posts.append(post_dict)
            POST_OPERATIONS.labels(action='hot', result='success').inc()
            return {
                'items':posts,
                'pagination':{'page':page,'per_page':per_page,'total':total}
            }
        except Exception:
            POST_OPERATIONS.labels(action='hot', result='error').inc()
            raise

