import logging
import time
import threading
from typing import Optional,List,Dict,Any
from core.redis_cache import redis_cache

logger=logging.getLogger(__name__)

class NotificationCache:
    '''
    通知缓存管理(对其PostCache/UserCache)

    缓存策略：
    -未读计数:user:{uid}:notif:unread
    -空缓存标记：user:{uid}:notif:empty
    -强一致标记：notif:recent_modify:{uid}(创建/标记已读/删除后)

    不缓存通知列表本身（实时性太高，缓存收益低、一致性成本高）
    '''
    UNREAD_TTL=60       #未读数缓存1分钟
    EMPTY_TTL=60        #空缓存防穿透60秒
    RECENT_MODIFY_TTL=60    #强一致窗口60秒

    @classmethod
    def _unread_key(cls,user_id:int):
        return f'user:{user_id}:notif:unread'
    
    @classmethod
    def _empty_key(cls,user_id:int):
        return f'user:{user_id}:notif:empty'
    
    @classmethod
    def _recent_key(cls,user_id:int):
        return f'notif:recent_modify:{user_id}'
    

    #==================未读计数缓存==================
    @classmethod
    def get_unread_count(cls,user_id:int):
        '''
        读未读数,
        返回None表示缓存未命中
        '''
        try:
            #先检查空缓存
            if redis_cache.get(cls._empty_key(user_id),for_write=False):
                return 0
            count=redis_cache.get(cls._unread_key(user_id),for_write=False)
            return int(count) if count is not None else None
        except Exception as e:
            logger.error(f'获取用户{user_id}未读数缓存失败：{e}')
            return None
        
    @classmethod
    def set_unread_count(cls, user_id: int, count: int) -> bool:
        """写未读数（走 Redis 主节点）"""
        try:
            return redis_cache.set(
                cls._unread_key(user_id),
                count,
                expire=cls.UNREAD_TTL,
                for_write=True
            )
        except Exception as e:
            logger.error(f'设置用户{user_id}未读数缓存失败: {e}')
            return False
    @classmethod
    def increment_unread(cls, user_id: int) -> bool:
        """新通知来时，未读数 +1（原子操作）"""
        try:
            # 如果缓存存在，直接原子 +1
            current = redis_cache.get(cls._unread_key(user_id), for_write=True)
            if current is not None:
                redis_cache.increment(cls._unread_key(user_id), amount=1)
                return True
            # 缓存不存在，不预热（等下次读时从 DB 聚合回填）
            return False
        except Exception as e:
            logger.error(f'递增用户{user_id}未读数失败: {e}')
            return False
    
    @classmethod
    def decrement_unread(cls,user_id:int):
        '''标记已读时，未读数-1(保底不小余0)'''
        try:
            current = redis_cache.get(cls._unread_key(user_id), for_write=True)
            if current is not None and int(current) > 0:
                # 用 Lua 保证原子性：大于 0 才减
                lua = """
                local current = redis.call('get', KEYS[1])
                if current and tonumber(current) > 0 then
                    return redis.call('decr', KEYS[1])
                else
                    return 0
                end
                """
                redis_cache.eval(lua, 1, cls._unread_key(user_id))
                return True
            return False
        except Exception as e:
            logger.error(f'递减用户{user_id}未读数失败: {e}')
            return False
    @classmethod
    def clear_unread(cls, user_id: int) -> bool:
        """全部已读：未读数清零"""
        try:
            redis_cache.set(
                cls._unread_key(user_id),
                0,
                expire=cls.UNREAD_TTL,
                for_write=True
            )
            return True
        except Exception as e:
            logger.error(f'清零用户{user_id}未读数失败: {e}')
            return False

    @classmethod
    def set_empty(cls, user_id: int) -> bool:
        """用户确实无通知时，标记空缓存防穿透"""
        try:
            redis_cache.set(
                cls._empty_key(user_id),
                "1",
                expire=cls.EMPTY_TTL,
                for_write=True
            )
            return True
        except Exception as e:
            logger.error(f'设置用户{user_id}通知空缓存失败: {e}')
            return False
    @classmethod
    def invalidate_empty(cls, user_id: int) -> bool:
        """有新通知时，清除空缓存标记"""
        try:
            redis_cache.delete(cls._empty_key(user_id))
            return True
        except Exception as e:
            logger.error(f'清除用户{user_id}通知空缓存失败: {e}')
            return False

    # ========== 强一致标记 ==========
    @classmethod
    def mark_recently_modified(cls, user_id: int, ttl: int = None) -> bool:
        """
        标记用户通知最近被修改（创建/标记已读/删除后）
        后续读未读数/列表强制走主库
        """
        ttl = ttl or cls.RECENT_MODIFY_TTL
        try:
            return redis_cache.set(
                cls._recent_key(user_id),
                "1",
                expire=ttl,
                for_write=True
            )
        except Exception as e:
            logger.error(f'标记用户{user_id}通知最近修改失败: {e}')
            return False

    @classmethod
    def is_recently_modified(cls, user_id: int) -> bool:
        """检查用户通知是否在强一致窗口内"""
        try:
            return redis_cache.exists(cls._recent_key(user_id)) > 0
        except Exception as e:
            logger.error(f'检查用户{user_id}通知最近修改失败: {e}')
            return False

    # ========== 延迟双删（未读计数） ==========

    @classmethod
    def double_invalidate_unread(cls, user_id: int):
        """
        标记已读/删除后的延迟双删
        第一次：立即删未读计数
        第二次：Celery 延迟 2 秒删
        """
        # 立即删除
        redis_cache.delete(cls._unread_key(user_id))
        redis_cache.delete(cls._empty_key(user_id))

        try:
            from core.celery_app import celery_app
            celery_app.send_task(
                'tasks.notification_tasks.delayed_invalidate_unread',
                args=(user_id,),
                countdown=2
            )
        except Exception as e:
            logger.warning(f'调度通知缓存延迟删除失败，降级为线程: {e}')
            cls._threaded_delayed_invalidate_unread(user_id)

    @classmethod
    def _threaded_delayed_invalidate_unread(cls, user_id: int):
        """线程降级：延迟 2 秒后再次删除"""
        def _delayed():
            time.sleep(2)
            cls.clear_unread(user_id)
            cls.invalidate_empty(user_id)
        threading.Thread(target=_delayed, daemon=True).start()

