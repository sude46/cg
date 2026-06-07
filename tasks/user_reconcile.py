from celery import shared_task
from app.users.cache import UserCache
from app.users.repositories import user_repository
from core.redis_cache import redis_cache
import logging
import random

logger = logging.getLogger(__name__)

@shared_task
def reconcile_user_cache(sample_size: int = 500):
    """
    定时对账：抽样比对 User Cache vs DB
    不一致则删缓存，下次请求自动回填
    """
    try:
        pattern = 'user:profile:*'
        keys = []
        for key in redis_cache.scan_iter(match=pattern, count=100):
            key_str = key.decode() if isinstance(key, bytes) else key
            keys.append(key_str)
        if not keys:
            return {'status': 'success', 'checked': 0, 'fixed': 0}
        if len(keys) > sample_size:
            keys = random.sample(keys, sample_size)

        fixed = 0
        checked = 0

        for key in keys:
            try:
                parts = key.split(':')
                if len(parts) < 3:
                    continue
                user_id = int(parts[-1])

                redis_data = UserCache.get_profile(user_id)
                if not redis_data:
                    continue

                db_user = user_repository.get_by_id(user_id, force_master=True)
                if not db_user:
                    UserCache.invalidate(user_id)
                    fixed += 1
                    continue

                checked += 1
                mismatched = False

                if redis_data.get('username') != db_user.username:
                    mismatched = True
                    logger.warning(f'[ReconcileUser] username 不一致 user_id={user_id}')

                redis_updated = redis_data.get('updated_at')
                db_updated = db_user.updated_at.isoformat() if db_user.updated_at else None
                if redis_updated and db_updated and redis_updated != db_updated:
                    mismatched = True
                    logger.warning(f'[ReconcileUser] updated_at 不一致 user_id={user_id}')

                redis_deleted = redis_data.get('deleted_at')
                db_deleted = db_user.deleted_at.isoformat() if db_user.deleted_at else None
                if redis_deleted != db_deleted:
                    mismatched = True

                if mismatched:
                    UserCache.invalidate(user_id)
                    fixed += 1
            except Exception as e:
                logger.error(f'[ReconcileUser] 对账单条异常 key={key}: {e}')
                continue

        logger.info(f'[ReconcileUser] 对账完成: 检查 {checked} 条, 修正 {fixed} 条')
        return {'status': 'success', 'checked': checked, 'fixed': fixed}
    except Exception as e:
        logger.error(f'[ReconcileUser] 对账任务异常: {e}')
        return {'status': 'failed', 'error': str(e)}
