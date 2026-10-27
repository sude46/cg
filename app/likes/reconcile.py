"""点赞对账的方向判定与主库计数。

对账的核心不是「Redis 和 DB 数字不一样就改 DB」，而是先判断 Redis 这份
计数是否完整可信：
- 缓存残缺/未知：DB 赢，用 DB 重建 Redis；
- 缓存完整且只多不少：才允许把 Redis 的增量补回 DB；
- 有在途任务（dirty key 还在）：本轮不动，留给下一轮。

这样冷启动时 Redis 从 1 开始，不会把 DB 的 500 覆盖成 1。
"""

import logging

from sqlalchemy import func

from app.likes.cache import LikeCache
from app.likes.models import Like
from core import db
from core.redis_cache import redis_cache

logger = logging.getLogger(__name__)

REBUILD_REDIS = "rebuild_redis"
UPDATE_DB = "update_db"
NOOP = "none"
DEFER = "defer"


def count_likes_from_master(target_type: str, target_id: int) -> int:
    """从主库统计有效点赞数（对账必须走主库，避免主从延迟制造假 diff）。"""
    query = db.session.query(func.count(Like.id)).filter(Like.deleted_at.is_(None))
    if target_type == "post":
        query = query.filter(Like.post_id == target_id)
    elif target_type == "comment":
        query = query.filter(Like.comment_id == target_id)
    else:
        raise ValueError(f"不支持的点赞目标类型: {target_type}")
    return int(query.scalar() or 0)


def read_redis_count_from_master(target_type: str, target_id: int):
    """从 Redis 主节点读取计数；count 不存在时与 LikeCache 语义一致地降级到 SCARD。"""
    count_key = LikeCache._like_count_key(target_type, target_id)
    raw = redis_cache.get(count_key, for_write=True)
    if raw is not None:
        return int(raw)

    likers_key = LikeCache._target_likers_key(target_type, target_id)
    if redis_cache.exists(likers_key, for_write=True) == 0:
        return None
    return int(redis_cache.scard(likers_key, for_write=True) or 0)


def cache_is_complete(target_type: str, target_id: int, redis_count) -> bool:
    """判断 Redis 的 likers 集合与计数是否互相印证。

    Redis 会整 key 淘汰，不会只淘汰 Set 的一半，因此「两个 key 都在且
    SCARD == count」是一个足够保守的完整性判据。判不了就返回 False，
    让对账走 DB -> Redis 重建。
    """
    if redis_count is None:
        return False
    try:
        count_key = LikeCache._like_count_key(target_type, target_id)
        likers_key = LikeCache._target_likers_key(target_type, target_id)
        if redis_cache.exists(count_key, for_write=True) == 0:
            return False
        if redis_cache.exists(likers_key, for_write=True) == 0:
            return False
        return int(redis_cache.scard(likers_key, for_write=True) or 0) == int(redis_count)
    except Exception as e:
        logger.warning(
            "[Reconcile] 判断缓存完整性失败 %s:%s: %s",
            target_type,
            target_id,
            e,
        )
        return False


def has_pending(target_type: str, target_id: int) -> bool:
    """per-target dirty key 还在说明点赞任务可能仍在途，本轮先不动。"""
    try:
        dirty_key = LikeCache._dirty_key(target_type, target_id)
        return redis_cache.exists(dirty_key, for_write=True) == 1
    except Exception as e:
        logger.warning(
            "[Reconcile] 读取 dirty 标记失败 %s:%s: %s，保守跳过",
            target_type,
            target_id,
            e,
        )
        return True


def decide_action(
    redis_count,
    db_count: int,
    cache_complete: bool,
    pending: bool,
) -> str:
    """纯函数：根据完整性/在途状态决定对账方向。"""
    if pending:
        return DEFER
    if redis_count is None or not cache_complete:
        return REBUILD_REDIS
    if redis_count < db_count:
        return REBUILD_REDIS
    if redis_count > db_count:
        return UPDATE_DB
    return NOOP
