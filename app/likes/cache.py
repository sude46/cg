import logging
import time

from redis.exceptions import NoScriptError

from core.redis_cache import redis_cache

logger = logging.getLogger(__name__)


# ========== Lua 脚本（原子更新 user/target/count/dirty 全部 key）==========
# KEYS: user_key, target_key, count_key, dirty_key, dirty_set
# ARGV: user_id, target_id, ttl, dirty_ttl, target_type, initial_count
LIKE_INCR_SCRIPT = """
local is_member = redis.call('SISMEMBER', KEYS[2], ARGV[1])
if is_member == 1 then
    return 0
end
if redis.call('EXISTS', KEYS[3]) == 0 then
    redis.call('SET', KEYS[3], ARGV[6], 'EX', ARGV[3])
end
redis.call('SADD', KEYS[2], ARGV[1])
redis.call('INCR', KEYS[3])
redis.call('SADD', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[3])
redis.call('EXPIRE', KEYS[3], ARGV[3])
redis.call('SETEX', KEYS[4], ARGV[4], '1')
redis.call('SADD', KEYS[5], ARGV[5] .. ':' .. ARGV[2])
return 1
"""

LIKE_DECR_SCRIPT = """
local is_member = redis.call('SISMEMBER', KEYS[2], ARGV[1])
if redis.call('EXISTS', KEYS[3]) == 0 then
    redis.call('SET', KEYS[3], ARGV[6], 'EX', ARGV[3])
end
if is_member == 1 then
    redis.call('SREM', KEYS[2], ARGV[1])
    local count = tonumber(redis.call('GET', KEYS[3]))
    if count and count > 0 then
        redis.call('DECR', KEYS[3])
    end
end
redis.call('SREM', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[2], ARGV[3])
redis.call('EXPIRE', KEYS[3], ARGV[3])
redis.call('SETEX', KEYS[4], ARGV[4], '1')
redis.call('SADD', KEYS[5], ARGV[5] .. ':' .. ARGV[2])
if is_member == 1 then return 1 end
return 2
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

    @classmethod
    def _eval_incr(cls, keys, args):
        """执行点赞 INCR 脚本；Redis 重启/切换导致脚本丢失(NOSCRIPT)时自动重载。"""
        try:
            return redis_cache.evalsha(cls._incr_sha, len(keys), *keys, *args)
        except NoScriptError:
            cls._incr_sha = redis_cache.script_load(LIKE_INCR_SCRIPT)
            return redis_cache.evalsha(cls._incr_sha, len(keys), *keys, *args)

    @classmethod
    def _eval_decr(cls, keys, args):
        """执行取消点赞 DECR 脚本；NOSCRIPT 时自动重载。"""
        try:
            return redis_cache.evalsha(cls._decr_sha, len(keys), *keys, *args)
        except NoScriptError:
            cls._decr_sha = redis_cache.script_load(LIKE_DECR_SCRIPT)
            return redis_cache.evalsha(cls._decr_sha, len(keys), *keys, *args)

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
    def is_liked(cls, user_id: int, target_id: int, target_type: str = 'post') -> bool | None:
        """
        检查是否已点赞（三态）
        - True/False：user_liked key 存在，按成员判断
        - None：key 不存在或 Redis 故障，需 Service 层降级查 DB
        """
        try:
            key = cls._user_liked_key(user_id, target_type)
            if redis_cache.exists(key, for_write=True) == 0:
                return None
            return bool(redis_cache.sismember(key, str(target_id), for_write=True))
        except Exception as e:
            logger.error(f'[Redis] 检查点赞状态失败 uid={user_id} tid={target_id}: {e}')
            return None

    @classmethod
    def get_like_count(cls, target_id: int, target_type: str = 'post') -> int | None:
        """
        获取点赞数量（优先读 String 计数器，O(1)）
        count 与 likers SCARD 不一致视为缓存不完整，返回 None；
        Counter 不存在时降级读 SCARD。
        """
        try:
            count_key = cls._like_count_key(target_type, target_id)
            likers_key = cls._target_likers_key(target_type, target_id)
            count = redis_cache.get(count_key, for_write=False)
            likers_exists = redis_cache.exists(likers_key, for_write=True)

            if count is not None:
                if likers_exists == 0:
                    return None
                scard = redis_cache.scard(likers_key, for_write=False)
                if scard is None or int(scard) != int(count):
                    return None
                return int(count)

            # Counter 不存在：likers Set 也不存在说明缓存未预热，返回 None 让上层用 DB 值
            if likers_exists == 0:
                return None
            # Set 存在：降级读 SCARD
            count = redis_cache.scard(likers_key, for_write=False)
            return int(count) if count is not None else None
        except Exception as e:
            logger.error(f'[Redis] 获取点赞数量失败 {target_type}:{target_id}: {e}')
            return None

    @classmethod
    def get_like_count_raw(cls, target_id: int, target_type: str = 'post') -> int | None:
        """只读原始 count，不做 SCARD 完整性校验（写路径发事件时用）。"""
        try:
            count = redis_cache.get(
                cls._like_count_key(target_type, target_id), for_write=True
            )
            return int(count) if count is not None else None
        except Exception as e:
            logger.error(f'[Redis] 获取原始点赞数量失败 {target_type}:{target_id}: {e}')
            return None

    @classmethod
    def get_liked_ids(cls, user_id: int, target_type: str = 'post') -> set[int]:
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
    def add_like(
        cls,
        user_id: int,
        target_id: int,
        target_type: str = 'post',
        expire: int = None,
        initial_count: int = 0,
    ) -> bool:
        """
        记录点赞到 Redis（Lua 原子脚本，一次覆盖全部 key）
        initial_count: count key 不存在时用于初始化，避免冷启动从 1 开始。
        """
        cls._load_scripts()
        expire = expire or cls.DEFAULT_EXPIRE
        try:
            keys = [
                cls._user_liked_key(user_id, target_type),
                cls._target_likers_key(target_type, target_id),
                cls._like_count_key(target_type, target_id),
                cls._dirty_key(target_type, target_id),
                "dirty:likes",
            ]
            args = [
                str(user_id),
                str(target_id),
                expire,
                cls.DIRTY_TTL,
                target_type,
                int(initial_count or 0),
            ]
            return cls._eval_incr(keys, args) == 1
        except Exception as e:
            logger.error(f'添加点赞缓存失败 uid={user_id} tid={target_id}: {e}')
            return False

    @classmethod
    def remove_like(
        cls,
        user_id: int,
        target_id: int,
        target_type: str = 'post',
        initial_count: int = 0,
    ) -> bool:
        """移除点赞记录；本来没点过也返回成功（幂等）。"""
        cls._load_scripts()
        try:
            keys = [
                cls._user_liked_key(user_id, target_type),
                cls._target_likers_key(target_type, target_id),
                cls._like_count_key(target_type, target_id),
                cls._dirty_key(target_type, target_id),
                "dirty:likes",
            ]
            args = [
                str(user_id),
                str(target_id),
                cls.DEFAULT_EXPIRE,
                cls.DIRTY_TTL,
                target_type,
                int(initial_count or 0),
            ]
            return cls._eval_decr(keys, args) in (1, 2)
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

    @classmethod
    def set_like_count(cls, target_id: int, count: int, target_type: str = 'post') -> bool:
        """以 DB 真值设置计数（回填校准用，避免 add_like 重复自增）"""
        try:
            count_key = cls._like_count_key(target_type, target_id)
            redis_cache.set(count_key, count, expire=cls.DEFAULT_EXPIRE, for_write=True)
            return True
        except Exception as e:
            logger.error(f'设置点赞计数失败 {target_type}:{target_id}: {e}')
            return False

    @classmethod
    def ensure_liker(cls, user_id: int, target_id: int, target_type: str = 'post') -> bool:
        """确保目标 likers Set 含该用户（回填关系用，不动计数）"""
        try:
            key = cls._target_likers_key(target_type, target_id)
            pipe = redis_cache.pipeline(transaction=False, for_write=True)
            pipe.sadd(key, str(user_id))
            pipe.expire(key, cls.DEFAULT_EXPIRE)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'回填 likers 关系失败 {target_type}:{target_id}: {e}')
            return False




