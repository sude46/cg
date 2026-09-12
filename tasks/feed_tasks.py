'''
Feed流异步任务
'''
import logging

from celery import shared_task

from app.feeds.cache import FeedCache

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
def async_push_to_followers(self, post_id: int, created_at: float, follower_ids: list[int]):
    '''
    异步推送到粉丝时间线（用于超大粉丝量的分批推送）
    当粉丝数极大时，同步推送会阻塞请求，改为异步任务分批执行
    '''
    try:
        result = FeedCache.push_to_followers(
            post_id=post_id,
            created_at=created_at,
            follower_ids=follower_ids
        )
        logger.info(
            f"异步推送完成：帖子{post_id}已推送到{result['pushed']}个粉丝"
        )
        return result
    except Exception as exc:
        logger.error(f'异步推送失败: {exc}')
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
