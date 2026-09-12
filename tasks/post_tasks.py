import logging

from celery import shared_task

from app.posts.cache import PostCache
from tasks.base_task import MonitoredTask

logger=logging.getLogger(__name__)

@shared_task(base=MonitoredTask,bind=True,max_retries=3,default_retry_delay=5)
def delayed_invalidate(self,post_id:int):
    """
    延迟双删的第二次删除
    由celery send_task 调度（countdown=2)
    """
    try:
        PostCache.invalidate(post_id)
        logger.info(f'[celery]延迟双删帖子缓存成功post_id={post_id}')
        return {'status':'success','post_id':post_id}
    except Exception as exc:
        logger.error(f'[celery]延迟删除帖子缓存失败post_id={post_id}:{exc}')
        raise self.retry(exc=exc)

@shared_task(base=MonitoredTask,bind=True,max_retries=3,default_retry_delay=5)
def delayed_invalidate_comment(self,comment_id:int):
    '''评论更新/删除后的延迟双删'''
    try:
        from app.comments.cache import CommentCache
        CommentCache.invalidate(comment_id)
        logger.info(f'[celery]延迟双删评论缓存成功comment_id={comment_id}')
        return {'status':'success','comment_id':comment_id}
    except Exception as exc:
        logger.error(f'[celery]延迟删除评论缓存失败:{exc}')
        return self.retry(exc=exc)
