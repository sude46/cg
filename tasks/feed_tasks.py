'''
Feed流异步任务
'''
import logging

from celery import shared_task

from app.feeds.cache import FeedCache
from app.follows.cache import FollowCache
from app.follows.repositories import follow_repository

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def async_remove_post_from_followers(self, post_id: int, follower_ids: list[int]):
    '''
    异步从所有粉丝时间线中移除帖子
    '''
    try:
        result = FeedCache.remove_post_from_all_followers(post_id, follower_ids)
        logger.info(
            f"异步任务完成：帖子{post_id}已从{result['removed_from']}/"
            f"{result['total_followers']}个粉丝时间线移除"
        )
        return {
            'task_id': self.request.id,
            'post_id': post_id,
            'removed_from': result['removed_from'],
            'total': result['total_followers'],
            'status': 'success'
        }
    except Exception as exc:
        logger.error(f'异步移除帖子失败，准备重试: {exc}')
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def async_push_to_followers(self, post_id: int, author_id: int, created_at: float):
    '''
    异步 fanout：帖子创建后推送到作者的所有粉丝时间线。

    任务体只接收 author_id（不接收粉丝列表）：粉丝列表在 worker 内查询并分批推送，
    避免把几十万粉丝 id 序列化进消息体撑爆 broker。
    粉丝缓存 miss 时回源从库并回填。
    '''
    try:
        # FollowCache 对 key 不存在返回空集合而非 None；本任务只对"粉丝>=异步阈值"的作者触发，
        # 因此取到空列表必是缓存未命中 -> 回源DB（否则会把帖子推给 0 个人）
        follower_ids = FollowCache.get_follower_ids(author_id)
        if not follower_ids:
            follower_ids = follow_repository.get_follower_ids(author_id)
            if follower_ids:
                FollowCache.preload_followers(author_id, follower_ids)
            logger.info(f'作者{author_id}粉丝缓存未命中，从DB加载{len(follower_ids)}人')

        if not follower_ids:
            logger.info(f'作者{author_id}无粉丝，帖子{post_id}无需fanout')
            return {'post_id': post_id, 'pushed': 0, 'mode': 'push', 'follower_count': 0}

        result = FeedCache.push_to_followers(
            post_id=post_id,
            created_at=created_at,
            follower_ids=follower_ids,
            follower_count=len(follower_ids),
        )
        logger.info(f"异步fanout完成：帖子{post_id}已推送到{result['pushed']}个粉丝")
        return result
    except Exception as exc:
        logger.error(f'异步fanout失败，准备重试: {exc}')
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3)
def async_invalidate_user_feed(self, user_id: int):
    '''
    异步清空用户时间线缓存
    用于批量操作（如管理员删除用户时）
    '''
    try:
        FeedCache.invalidate_feed(user_id)
        logger.info(f'异步清空用户{user_id}时间线缓存完成')
        return {'user_id': user_id, 'invalidated': True}
    except Exception as exc:
        logger.error(f'清空缓存失败: {exc}')
        raise self.retry(exc=exc)
