import logging

from core.redis_cache import redis_cache

logger = logging.getLogger(__name__)


class AccountLockService:
    """
    登录失败计数 + 账户锁定（基于 Redis，不写 DB）
    ================================================
    key: login:fail:{user_id}     → 失败次数（INCR, TTL=20min）
    key: login:lock:{user_id}    → 锁定标记（SETEX, TTL=20min）

    为什么用 Redis 替代 DB 字段：
    - 登录失败是高频写操作，不应加重 MySQL 写负载
    - 计数天然带 TTL 自动过期，无需定时清理锁
    - 防止 UserCache._sanitize 与 Schema 之间的过滤不一致
    """

    MAX_LOGIN_FAILS = 5
    LOCK_DURATION_MINUTES = 20
    LOCK_TTL = LOCK_DURATION_MINUTES * 60

    @classmethod
    def _fail_key(cls, user_id: int) -> str:
        return f'login:fail:{user_id}'

    @classmethod
    def _lock_key(cls, user_id: int) -> str:
        return f'login:lock:{user_id}'

    @classmethod
    def is_locked(cls, user_id: int) -> bool:
        try:
            return redis_cache.exists(cls._lock_key(user_id)) > 0
        except Exception as e:
            logger.error(f'检查锁定状态失败 user_id={user_id}: {e}')
            return False

    @classmethod
    def record_failed_attempt(cls, user_id: int):
        try:
            count = redis_cache.increment(cls._fail_key(user_id), 1)
            # 第一次失败时设置 TTL（Redis INCR 不会自动设 TTL）
            if count == 1:
                redis_cache.expire(cls._fail_key(user_id), cls.LOCK_TTL)
            if count >= cls.MAX_LOGIN_FAILS:
                redis_cache.set(
                    cls._lock_key(user_id),
                    '1',
                    expire=cls.LOCK_TTL,
                    for_write=True
                )
                logger.warning(f'账户已锁定 user_id={user_id}，持续 {cls.LOCK_DURATION_MINUTES} 分钟')
        except Exception as e:
            logger.error(f'记录登录失败失败 user_id={user_id}: {e}')

    @classmethod
    def reset_attempts(cls, user_id: int):
        try:
            redis_cache.delete(cls._fail_key(user_id))
            redis_cache.delete(cls._lock_key(user_id))
        except Exception as e:
            logger.error(f'重置登录计数失败 user_id={user_id}: {e}')
