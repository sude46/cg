from celery import shared_task
from app.users.cache import UserCache
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def delayed_invalidate(self, user_id: int, username: str = None, email: str = None):
    """
    延迟双删的第二次删除
    由 celery send_task 调度（countdown=2）
    """
    try:
        UserCache.invalidate(user_id)
        if username:
            UserCache.invalidate_by_username(username)
        if email:
            UserCache.invalidate_by_email(email)
        logger.info(f'[celery]延迟双删用户缓存成功 user_id={user_id}')
        return {'status': 'success', 'user_id': user_id}
    except Exception as exc:
        logger.error(f'[celery]延迟删除用户缓存失败 user_id={user_id}: {exc}')
        raise self.retry(exc=exc)
