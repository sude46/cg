import logging
from typing import List,Optional
from core.redis_cache import redis_cache

logger=logging.getLogger(__name__)

class FollowCache:
    '''
    关注关系缓存(set结构)
    -following:{uid} ->Set of followed_id(我关注谁)
    -followers:{uid}->Set of follower_id(谁关注我)

    用途：
    1.is_following O(1)查关注状态
    2.get_followers 获取粉丝列表(Feed推送用，避免DB全表扫)
    '''

    TTL_DAYS=30
    LOCK_TTL=10

    @classmethod
    def _following_key(cls,user_id:int):
        return f'following:{user_id}'
    
    @classmethod
    def _followers_key(cls,user_id:int):
        return f'followers:{user_id}'
    
    @classmethod
    def _lock_key(cls, follower_id: int, followed_id: int) -> str:
        return f'lock:follow:{follower_id}:{followed_id}'
    
    @classmethod
    def acquire_lock(cls, follower_id: int, followed_id: int) -> bool:
        """获取分布式锁，防止并发重复关注/取关"""
        return redis_cache.setnx(
            cls._lock_key(follower_id, followed_id),
            "1",
            expire=cls.LOCK_TTL
        )

    @classmethod
    def release_lock(cls, follower_id: int, followed_id: int) -> bool:
        """释放分布式锁"""
        return redis_cache.delete(cls._lock_key(follower_id, followed_id)) 
    
    #=============读操作=============
    @classmethod
    def  is_following(cls,follower_id:int,followed_id:int):
        '''是否已关注(None表示Redis故障，需降级查DB)'''
        try:
            result=redis_cache.sismember(
                cls._following_key(follower_id),
                str(followed_id),
                for_write=False
            )
            return bool(result)
        except Exception as e:
            logger.error(f'[FollowCache]查关注状态失败{follower_id}->{followed_id}:{e}')
            return None
    
    @classmethod
    def get_following_ids(cls,user_id:int):
        '''获取关注列表(None表示miss或故障)'''
        try:
            members=redis_cache.smembers(
                cls._following_key(user_id),
                for_write=False
            )
            if members is None:
                return None
            return[
                int(m.decode() if isinstance(m,bytes) else m)
                for m in members
            ]
        except Exception as e:
            logger.error(f'[FollowCache]词查关注列表失败 uid={user_id}:{e}')
            return None
        
    @classmethod
    def get_follower_ids(cls, user_id: int) -> Optional[List[int]]:
        """获取粉丝列表（Feed 推送用）"""
        try:
            members = redis_cache.smembers(
                cls._followers_key(user_id),
                for_write=False
            )
            if members is None:
                return None
            return [
                int(m.decode() if isinstance(m, bytes) else m)
                for m in members
            ]
        except Exception as e:
            logger.error(f'[FollowCache] 查粉丝列表失败 uid={user_id}: {e}')
            return None
        
    #==========写操作
    @classmethod
    def add_relation(cls,follower_id:int,followed_id:int):
        '''关注后同步写缓存'''
        try:
            pipe=redis_cache.pipeline(transaction=False,for_write=True)
            pipe.sadd(cls._following_key(follower_id),str(followed_id))
            pipe.sadd(cls._followers_key(followed_id),str(follower_id))
            pipe.expire(cls._following_key(followed_id),cls.TTL_DAYS*86400)
            pipe.expire(cls._followers_key(followed_id), cls.TTL_DAYS * 86400)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'[FollowCache] 添加关系失败 {follower_id}->{followed_id}: {e}')
            return False
    @classmethod
    def remove_relation(cls, follower_id: int, followed_id: int) -> bool:
        """取关后同步清缓存"""
        try:
            pipe = redis_cache.pipeline(transaction=False, for_write=True)
            pipe.srem(cls._following_key(follower_id), str(followed_id))
            pipe.srem(cls._followers_key(followed_id), str(follower_id))
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'[FollowCache] 移除关系失败 {follower_id}->{followed_id}: {e}')
            return False
    @classmethod
    def preload_followers(cls,user_id:int,follower_ids):
        '''DB回填Redis(发帖推送前预热)'''
        if not follower_ids:
            return True
        try:
            pipe=redis_cache.pipeline(transaction=False,for_write=True)
            pipe.sadd(cls._followers_key(user_id),*[str(i) for i in follower_ids])
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'[FollowCache] 预热粉丝失败 uid={user_id}: {e}')
            return False
    @classmethod
    def invalidate(cls, user_id: int) -> bool:
        """清空用户缓存（异常时兜底）"""
        try:
            pipe = redis_cache.pipeline(transaction=False, for_write=True)
            pipe.delete(cls._following_key(user_id))
            pipe.delete(cls._followers_key(user_id))
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'[FollowCache] 清空缓存失败 uid={user_id}: {e}')
            return False

        

        
    