from typing import Set, Optional
from core.redis_cache import redis_cache
import logging
import time

logger = logging.getLogger(__name__)


# ========== Lua 脚本（原子更新 Set + Counter）==========
LIKE_INCR_SCRIPT = """
local is_member = redis.call('sismember', KEYS[1], ARGV[1])
if is_member == 0 then
    redis.call('sadd', KEYS[1], ARGV[1])
    redis.call('incr', KEYS[2])
    return 1
end
return 0
"""

LIKE_DECR_SCRIPT = """
local is_member = redis.call('sismember', KEYS[1], ARGV[1])
if is_member == 1 then
    redis.call('srem', KEYS[1], ARGV[1])
    redis.call('decr', KEYS[2])
    return 1
end
return 0
"""


class LikeCache:
    """
    点赞相关的 Redis 缓存（工业级）
    - Set: user:{uid}:liked_posts      # 用户点过赞的帖子 ID 集合
    - Set: post:{pid}:likers            # 帖子的点赞用户 ID 集合
    - String: post:{pid}:like_count     # 帖子点赞计数（O(1) 读取）
    - String: post:{pid}:like_count:dirty # 脏标记，触发异步回写 DB
    """

    DEFAULT_EXPIRE = 86400 * 7  # 默认 7 天
    DIRTY_TTL = 300             # 脏标记 5 分钟内同步回库
    LOCK_TTL = 10               # 分布式锁 10 秒

    # 脚本 sha1 缓存（类级别，避免每次重复加载）
    _incr_sha = None
    _decr_sha = None

    @classmethod
    def _load_scripts(cls):
        """延迟加载 Lua 脚本（只执行一次）"""
        if cls._incr_sha is None:
            cls._incr_sha = redis_cache.script_load(LIKE_INCR_SCRIPT)
        if cls._decr_sha is None:
            cls._decr_sha = redis_cache.script_load(LIKE_DECR_SCRIPT)

    # ========== Key 生成 ==========

    @classmethod
    def _user_liked_key(cls, user_id: int, target_type: str) -> str:
        return f'user:{user_id}:liked_{target_type}s'

    @classmethod
    def _target_likers_key(cls, target_type: str, target_id: int) -> str:
        return f'{target_type}:{target_id}:likers'

    @classmethod
    def _like_count_key(cls, target_type: str, target_id: int) -> str:
        return f'{target_type}:{target_id}:like_count'

    @classmethod
    def _dirty_key(cls, target_type: str, target_id: int) -> str:
        return f'{target_type}:{target_id}:like_count:dirty'

    @classmethod
    def _lock_key(cls, user_id: int, target_id: int, target_type: str) -> str:
        return f'lock:like:{target_type}:{target_id}:{user_id}'

    # ========== 分布式锁 ==========

    @classmethod
    def acquire_lock(cls, user_id: int, target_id: int, target_type: str = 'post'):
        """获取分布式锁，防止并发重复点赞"""
        lock_key = cls._lock_key(user_id, target_id, target_type)
        return redis_cache.setnx(lock_key, str(int(time.time())), expire=cls.LOCK_TTL)

    @classmethod
    def release_lock(cls, user_id: int, target_id: int, target_type: str = 'post'):
        """释放分布式锁"""
        lock_key = cls._lock_key(user_id, target_id, target_type)
        redis_cache.delete(lock_key)

    # ========== 读操作（走从库，故障返回 None 降级） ==========

    @classmethod
    def is_liked(cls, user_id: int, target_id: int, target_type: str = 'post') -> Optional[bool]:
        """
        检查是否已点赞
        返回 True/False，或 None（Redis 故障，需 Service 层降级查 DB）
        """
        try:
            result = redis_cache.sismember(
                cls._user_liked_key(user_id, target_type),
                str(target_id),
                for_write=False
            )
            return bool(result)
        except Exception as e:
            logger.error(f'[Redis] 检查点赞状态失败 uid={user_id} tid={target_id}: {e}')
            return None

    @classmethod
    def get_like_count(cls, target_id: int, target_type: str = 'post') -> Optional[int]:
        """
        获取点赞数量（优先读 String 计数器，O(1)）
        如果 Counter 键不存在，降级读 SCARD
        """
        try:
            count_key = cls._like_count_key(target_type, target_id)
            count = redis_cache.get(count_key, for_write=False)
            if count is not None:
                return int(count)
            # Counter 不存在，降级读 SCARD
            count = redis_cache.scard(
                cls._target_likers_key(target_type, target_id),
                for_write=False
            )
            return int(count) if count is not None else 0
        except Exception as e:
            logger.error(f'[Redis] 获取点赞数量失败 {target_type}:{target_id}: {e}')
            return None

    @classmethod
    def get_liked_ids(cls, user_id: int, target_type: str = 'post') -> Set[int]:
        """
        获取用户已点赞的所有 ID（批量查询优化）
        返回空 set（无数据或异常），Service 层无需处理 None
        """
        try:
            members = redis_cache.smembers(
                cls._user_liked_key(user_id, target_type),
                for_write=False
            )
            if not members:
                return set()
            return {
                int(m.decode() if isinstance(m, bytes) else m)
                for m in members
            }
        except Exception as e:
            logger.error(f'[Redis] 获取用户点赞列表失败 uid={user_id}: {e}')
            return set()

    # ========== 写操作（Lua 原子更新 Set + Count + 脏标记） ==========

    @classmethod
    def add_like(cls, user_id: int, target_id: int, target_type: str = 'post', expire: int = None) -> bool:
        """
        记录点赞到 Redis（Lua 原子脚本）
        返回 True（成功）/ False（失败或已点过）
        """
        cls._load_scripts()
        expire = expire or cls.DEFAULT_EXPIRE
        try:
            user_key = cls._user_liked_key(user_id, target_type)
            target_key = cls._target_likers_key(target_type, target_id)
            count_key = cls._like_count_key(target_type, target_id)
            dirty_key = cls._dirty_key(target_type, target_id)

            # 1) Lua 原子更新：Set + Counter
            result = redis_cache.evalsha(
                cls._incr_sha,
                2,
                target_key,
                count_key,
                str(user_id)
            )
            if result == 0:
                return False  # 已点过赞，幂等返回

            # 2) Pipeline 设置过期时间和脏标记
            pipe = redis_cache.pipeline(transaction=False, for_write=True)
            pipe.sadd(user_key, str(target_id))
            pipe.expire(user_key, expire)
            pipe.expire(target_key, expire)
            pipe.expire(count_key, expire)
            pipe.setex(dirty_key, cls.DIRTY_TTL, '1')
            pipe.sadd("dirty:likes", f"{target_type}:{target_id}")
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'添加点赞缓存失败 uid={user_id} tid={target_id}: {e}')
            return False

    @classmethod
    def remove_like(cls, user_id: int, target_id: int, target_type: str = 'post') -> bool:
        """移除点赞记录"""
        cls._load_scripts()
        try:
            user_key = cls._user_liked_key(user_id, target_type)
            target_key = cls._target_likers_key(target_type, target_id)
            count_key = cls._like_count_key(target_type, target_id)
            dirty_key = cls._dirty_key(target_type, target_id)

            result = redis_cache.evalsha(
                cls._decr_sha,
                2,
                target_key,
                count_key,
                str(user_id)
            )
            if result == 0:
                return False  # 本来就没点过

            pipe = redis_cache.pipeline(transaction=False, for_write=True)
            pipe.srem(user_key, str(target_id))
            pipe.expire(target_key, cls.DEFAULT_EXPIRE)
            pipe.expire(count_key, cls.DEFAULT_EXPIRE)
            pipe.setex(dirty_key, cls.DIRTY_TTL, '1')
            pipe.sadd("dirty:likes", f"{target_type}:{target_id}")
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'移除点赞缓存失败 uid={user_id} tid={target_id}: {e}')
            return False

    @classmethod
    def delete_dirty(cls, target_type: str, target_id: int) -> bool:
        """删除脏标记"""
        try:
            dirty_key = cls._dirty_key(target_type, target_id)
            redis_cache.delete(dirty_key)
            return True
        except Exception as e:
            logger.error(f'删除脏标记失败 {target_type}:{target_id}: {e}')
            return False

    # ========== 预加载（回填用，加分布式锁防并发） ==========

    @classmethod
    def preload_user_likes(cls, user_id: int, liked_ids: list, target_type: str = 'post') -> bool:
        """
        预加载用户点赞状态到 Redis（批量优化，DB 查询后回填）
        加分布式锁：防止回填过程用户有新点赞，导致 DB 与 Redis 不一致
        """
        if not liked_ids:
            return True

        lock_key = f"preload:user_likes:{user_id}"
        acquired = False

        try:
            acquired = redis_cache.setnx(lock_key, "1", expire=60)
            if not acquired:
                logger.warning(f"[Preload] user_likes {user_id} 正在回填，跳过")
                return False

            key = cls._user_liked_key(user_id, target_type)
            pipe = redis_cache.pipeline(transaction=False, for_write=True)
            pipe.sadd(key, *[str(i) for i in liked_ids])
            pipe.expire(key, cls.DEFAULT_EXPIRE)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'预加载用户 {user_id} 点赞状态失败: {e}')
            return False
        finally:
            if acquired:
                redis_cache.delete(lock_key)

    @classmethod
    def preload_target_likers(cls, target_id: int, liker_ids: list, target_type: str = 'post') -> bool:
        """
        预加载目标点赞者到 Redis（DB 查询后回填）
        加分布式锁：防止回填过程中有新点赞进来导致 Set 与 Counter 不一致
        回填时直接以 DB 数据为准设置 like_count，不依赖 SCARD
        """
        lock_key = f"preload:target_likers:{target_type}:{target_id}"
        acquired = False

        try:
            acquired = redis_cache.setnx(lock_key, "1", expire=60)
            if not acquired:
                logger.warning(f"[Preload] target_likers {target_type}:{target_id} 正在回填，跳过")
                return False

            target_key = cls._target_likers_key(target_type, target_id)
            count_key = cls._like_count_key(target_type, target_id)

            pipe = redis_cache.pipeline(transaction=False, for_write=True)
            if liker_ids:
                pipe.sadd(target_key, *[str(i) for i in liker_ids])
                pipe.expire(target_key, cls.DEFAULT_EXPIRE)
                pipe.setex(count_key, cls.DEFAULT_EXPIRE, str(len(liker_ids)))
            else:
                pipe.delete(target_key)
                pipe.setex(count_key, cls.DEFAULT_EXPIRE, "0")
            pipe.execute()

            logger.info(
                f"[Preload] {target_type}:{target_id} 点赞者回填完成，"
                f"共 {len(liker_ids)} 人，Counter={len(liker_ids)}"
            )
            return True
        except Exception as e:
            logger.error(f'预加载目标 {target_id} 点赞者失败: {e}')
            return False
        finally:
            if acquired:
                redis_cache.delete(lock_key)

    @classmethod
    def _reset_count(cls, target_type: str, target_id: int) -> bool:
        """清空计数（用于 DB 为空时的兜底）"""
        try:
            count_key = cls._like_count_key(target_type, target_id)
            redis_cache.set(count_key, 0, expire=cls.DEFAULT_EXPIRE, for_write=True)
            return True
        except Exception as e:
            logger.error(f'重置计数失败 {target_type}:{target_id}: {e}')
            return False


        

