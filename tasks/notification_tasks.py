import logging

from celery import shared_task

from app.notifications.cache import NotificationCache

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def delayed_invalidate_unread(self, user_id: int):
    """
    延迟双删未读计数（第二次删除）
    由 NotificationCache.double_invalidate_unread 调度（countdown=2）
    """
    try:
        NotificationCache.invalidate_unread(user_id)
        logger.info(f'[celery]延迟双删通知缓存成功 user_id={user_id}')
        return {'status': 'success', 'user_id': user_id}
    except Exception as exc:
        logger.error(f'[celery]延迟删除通知缓存失败 user_id={user_id}: {exc}')
        raise self.retry(exc=exc)
