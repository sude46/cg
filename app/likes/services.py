import logging
import time
from datetime import UTC, datetime

from app.comments.repositories import comment_repository
from app.common import event_bus
from app.common.exceptions import (
    ConflictError,
    DatabaseError,
    PermissionError,
    ResourceNotFoundError,
    ValidationError,
)
from app.likes.cache import LikeCache
from app.likes.repositories import like_repository
from app.posts.repositories import post_repository
from app.users.repositories import user_repository
from core.metrics import CELERY_TASKS, LIKE_OPERATIONS, REDIS_HIT_RATE

from .schemas import like_schema, likes_schema

logger = logging.getLogger(__name__)



class LikeService:
    @staticmethod
    def create_like(user_id: int, post_id: int = None, comment_id: int = None):
        """创建点赞，返回序列化字典"""
        if not (post_id or comment_id) or (post_id and comment_id):
            raise ValidationError('只能传入 post_id 或 comment_id')
        target_type='post' if post_id else 'comment'
        target_id=post_id or comment_id

        # 校验主体与目标存在（避免给不存在的对象点赞）
        if not user_repository.get_by_id(user_id):
            raise ResourceNotFoundError('用户不存在')
        target_owner_id=None
        if post_id:
            target_post=post_repository.get_by_id(post_id)
            if not target_post:
                raise ResourceNotFoundError('帖子不存在')
            target_owner_id=target_post.user_id
        if comment_id:
            target_comment=comment_repository.get_by_id(comment_id)
            if not target_comment:
                raise ResourceNotFoundError('评论不存在')
            target_owner_id=target_comment.user_id

        #分布式锁防并发重复点赞(10秒TTL)
        if not LikeCache.acquire_lock(user_id,target_id,target_type):
            raise ConflictError('操作过于频繁，请稍后重试')

        try:
            #先查redis
            cached_liked=LikeCache.is_liked(user_id,target_id,target_type)

            #记录缓存命中率(1=命中，0=miss/故障)
            REDIS_HIT_RATE.labels(cache_type="like").set(
                    1 if cached_liked is not None else 0
                    )
            if cached_liked is True:
                LIKE_OPERATIONS.labels(action='create',result='duplicate').inc()
                raise ConflictError('您已点赞过了')

            #Redis故障或miss,降级查DB
            if cached_liked is None:
                if post_id:
                    existing_like=like_repository.get_post_like(user_id,post_id)
                else:
                    existing_like=like_repository.get_comment_like(user_id,comment_id)
                if existing_like:
                    #DB有但Redis丢了：只回填关系，计数以DB真值为准（不能 add_like 再+1）
                    LikeCache.preload_user_likes(user_id,[target_id],target_type)
                    LikeCache.ensure_liker(user_id,target_id,target_type)
                    if target_type=='post':
                        db_count=like_repository.count_likes_for_post(target_id)
                    else:
                        db_count=like_repository.count_likes_for_comment(target_id)
                    LikeCache.set_like_count(target_id,db_count,target_type)
                    LIKE_OPERATIONS.labels(action='create',result='duplicate').inc()
                    raise ConflictError('您已点赞过了')


            #核心：先写redis
            if not LikeCache.add_like(user_id,target_id,target_type):
                LIKE_OPERATIONS.labels(action='create',result='error').inc()
                raise DatabaseError('点赞操作失败，请稍后重试')

            #异步刷DB(Celery任务，pending_id幂等去重)
            pending_id=f'like:{user_id}:{target_type}:{target_id}:{int(time.time()*1000)}'
            try:
                from tasks.like_tasks import async_like_to_do
                async_like_to_do.delay(user_id=user_id,target_id=target_id,target_type=target_type,action='create',pending_id=pending_id)
                CELERY_TASKS.labels(
                        task_name='async_like_to_do',status='published').inc()
            except Exception as e:
                CELERY_TASKS.labels(
                        task_name='async_like_to_do',status='publish_failed').inc()
                #Celery投递失败不阻塞用户，靠服务端对账兜底
                logger.error(f'[LikeService] Celery投递失败pending_id: {pending_id}, error: {e}')

            #热评实时更新
            if target_type=='comment':
                from app.comments.cache import CommentCache
                comment=comment_repository.get_by_id(target_id,force_master=False)
                if comment:
                    new_count=LikeCache.get_like_count(target_id,'comment') or 0
                    CommentCache.update_hot_comment(comment.post_id,target_id,new_count)

            #异步更新ES（用redis实时计数，不阻塞主流程)
            if post_id:
                like_count=LikeCache.get_like_count(post_id,'post') or 0
                event_bus.publish('post.like_count_changed',{
                    'post_id':post_id,
                    'like_count':like_count
                })
                LIKE_OPERATIONS.labels(action='create',result='success').inc()
                logger.info(f'[LikeService]用户{user_id}点赞成功(redis秒返回),pending_id: {pending_id}')

            # 通知模块订阅：给内容作者建通知（自己赞自己不通知）
            if target_owner_id and target_owner_id!=user_id:
                try:
                    event_bus.publish('like.created',{
                        'user_id':target_owner_id,
                        'actor_id':user_id,
                        'type':'like',
                        'post_id':post_id,
                        'comment_id':comment_id,
                        'target_type':target_type,
                    })
                except Exception as e:
                    logger.warning(f'发布点赞事件失败（不影响主流程）：{e}')

            return like_schema.dump({
                'user_id': user_id,
                'post_id': post_id,
                'comment_id': comment_id,
                'created_at': datetime.now(UTC)
            })
        except ConflictError:
            raise
        except Exception:
            LIKE_OPERATIONS.labels(action='create',result='error').inc()
            raise

        finally:
            # 确保锁释放（无论成功失败）
            LikeCache.release_lock(user_id, target_id, target_type)


    @staticmethod
    def delete_like(user_id: int, post_id: int = None, comment_id: int = None):
        """取消点赞，返回 True/False"""
        if not (post_id or comment_id) or (post_id and comment_id):
            raise ValidationError('必须且只能传入 post_id 或 comment_id')
        target_type='post' if post_id else 'comment'
        target_id=post_id or comment_id

        #分布式锁
        if not LikeCache.acquire_lock(user_id,target_id,target_type):
            raise ConflictError('操作过于频繁，请稍后重试')

        try:
            #先查Redis
            cached_liked=LikeCache.is_liked(user_id,target_id,target_type)
            REDIS_HIT_RATE.labels(cache_type='like').set(
                    1 if cached_liked is not None else 0
                    )

            if cached_liked is False:
                LIKE_OPERATIONS.labels(action='delete',result='not_found').inc()
                raise ResourceNotFoundError('点赞记录不存在')
            #Redis故障降级查DB
            elif cached_liked is None:
                if post_id:
                    like=like_repository.get_post_like(user_id,post_id)
                else:
                    like=like_repository.get_comment_like(user_id,comment_id)
                if not like:
                    LIKE_OPERATIONS.labels(action='delete',result='not_found').inc()
                    raise ResourceNotFoundError('点赞记录不存在')
                #DB有但Redis丢了：只回填关系并用DB真值校准计数，随后 remove_like 正常 -1
                LikeCache.preload_user_likes(user_id,[target_id],target_type)
                LikeCache.ensure_liker(user_id,target_id,target_type)
                if target_type=='post':
                    db_count=like_repository.count_likes_for_post(target_id)
                else:
                    db_count=like_repository.count_likes_for_comment(target_id)
                LikeCache.set_like_count(target_id,db_count,target_type)
            #cache_liked is True 或者None但已回填，都继续执行删除
            #先删redis(秒返回)
            if not LikeCache.remove_like(user_id,target_id,target_type):
                LIKE_OPERATIONS.labels(action='delete',result='error').inc()
                raise DatabaseError('取消点赞操作失败，请稍后重试')
            #异步删DB(Celery任务，pending_id幂等去重)
            pending_id=f'unlike:{user_id}:{target_type}:{target_id}:{int(time.time()*1000)}'
            try:
                from tasks.like_tasks import async_like_to_do
                async_like_to_do.delay(user_id=user_id,target_id=target_id,target_type=target_type,action='delete',pending_id=pending_id)
                CELERY_TASKS.labels(
                        task_name='async_like_to_do',status='published'
                        ).inc()
            except Exception as e:
                CELERY_TASKS.labels(
                        task_name='async_like_to_do',status='publish_failed'
                        ).inc()
                logger.error(f'[LikeService] Celery投递失败pending_id: {pending_id}, error: {e}')

            #热评移除
            if target_type == 'comment':
                from app.comments.cache import CommentCache
                comment = comment_repository.get_by_id(target_id, force_master=False)
                if comment:
                    new_count = LikeCache.get_like_count(target_id, 'comment') or 0
                    # like_count 为 0 时从热评榜移除
                    CommentCache.update_hot_comment(comment.post_id, target_id, new_count)

            #异步更新ES（用redis实时计数，不阻塞主流程)
            if post_id:
                like_count=LikeCache.get_like_count(post_id,'post') or 0
                event_bus.publish('post.like_count_changed',{
                    'post_id':post_id,
                    'like_count':like_count
                })
                logger.info(f'[LikeService]用户{user_id}取消点赞成功(redis秒返回),pending_id: {pending_id}')
            elif comment_id:
                like_count=LikeCache.get_like_count(comment_id,'comment') or 0
                event_bus.publish('comment.like_count_changed',{
                    'comment_id':comment_id,
                    'like_count':like_count
                })
                LIKE_OPERATIONS.labels(action='delete',result='success').inc()
                logger.info(f'[LikeService]用户{user_id}取消点赞成功(redis秒返回),pending_id: {pending_id}')
            return True
        except ResourceNotFoundError:
            raise
        except Exception:
            LIKE_OPERATIONS.labels(action='delete', result='error').inc()
            raise

        finally:
            LikeCache.release_lock(user_id,target_id,target_type)

    @staticmethod
    def delete_like_by_id(user_id: int, like_id: int, post_id: int = None):
        """通过 like_id 删除点赞，需验证用户权限"""
        like = like_repository.get_by_id(like_id, force_master=True)
        if not like:
            raise ResourceNotFoundError('点赞记录不存在')
        if like.user_id != user_id:
            raise PermissionError('无权限取消该点赞')
        if post_id and like.post_id!=post_id:
            raise ResourceNotFoundError('点赞记录和帖子不匹配')
        #复用delete_like的逻辑
        return LikeService.delete_like(user_id,post_id=like.post_id,comment_id=like.comment_id)
    @staticmethod
    def get_user_likes(user_id: int, page: int = 1, per_page: int = 20):
        user = user_repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError('用户不存在')
        per_page = min(100, max(1, per_page))
        result = like_repository.list_by_user(user_id, page=page, per_page=per_page)
        likes_data = likes_schema.dump(result['items'], many=True)
        return {
            'items': likes_data,
            'pagination': result['pagination']
        }

