from typing import Set,Optional
from core.redis_cache import redis_cache
from typing import Set
import logging

logger=logging.getLogger(__name__)

class LikeCache:
    '''
    点赞相关的Redis缓存(放重复、技术加速)
    
    数据结构：
    -Set:user:{uid}:liked_posts      #用户点过赞的帖子ID集合
    -Set:post:{pid}:likers           #帖子的点赞用户ID集合(用于快速计数)
    -String:post:{pid}:like_count:dirty      #脏标记，触发异步回写数据库
    '''

    DEFAULT_EXPIRE=86400*7     #默认7天
    DIRTY_TTL=300              #脏标记5分钟内同步回库



    @classmethod
    def _user_liked_key(cls,user_id:int,target_type:str):
        '''用户已点赞集合的key'''
        return f'user:{user_id}:liked_{target_type}s'
    
    @classmethod
    def _target_likers_key(cls,target_type:str,target_id:int):
        '''目标点赞者集合的key（用于统计和防刷)'''
        return f'{target_type}:{target_id}:likers'
    
    @classmethod
    def is_liked(cls,user_id:int,target_id:int,target_type:str='post'):
        '''快速检查是否已点赞(Redis 层拦截，避免查库)'''
        try:
            #sismemeber 返回0/1,转bool
            return bool(redis_cache.sismember(
                cls._user_liked_key(user_id,target_type),
                str(target_id)
            ))
        except Exception as e:
            logger.error(f'检查点赞状态失败uid={user_id} tid={target_id}:{e}')
            return False
        
    
    @classmethod
    def add_like(cls,user_id:int,target_id:int,target_type:str='post',expire:int=86400*7):
        '''记录点赞到redis(同时维护双向关系)'''
        try:
            user_key=cls._user_liked_key(user_id,target_type)
            target_key=cls._target_likers_key(target_type,target_id)
            counter_key=f'{target_type}:{target_id}:like_count:dirty'
            
            pipe=redis_cache.pipeline(transaction=False)
            pipe.sadd(user_key,str(target_id))
            pipe.expire(user_key,expire)
            pipe.sadd(target_key,str(user_id))
            pipe.expire(target_key,expire)
            pipe.setex(counter_key,expire,'1')
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'添加点赞缓存失败 uid={user_id} tid={target_id}:{e}')
            return False
        

    @classmethod
    def remove_like(cls,user_id:int,target_id:int,target_type:str='post'):
        '''移除点赞记录'''
        try:
            user_key=cls._user_liked_key(user_id,target_type)
            target_key=cls._target_likers_key(target_type,target_id)
            counter_key=f'{target_type}:{target_id}:like_count:dirty'

            pipe=redis_cache.pipeline(transaction=False)
            pipe.srem(user_key,str(target_id))
            pipe.srem(target_key,str(user_id))
            pipe.setex(counter_key,cls.DIRTY_TTL,'1')
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'移除点赞缓存失败 uid={user_id} tid={target_id}:{e}')
            return False
        

    
    @classmethod
    def get_liked_ids(cls,user_id:int,target_type:str='post'):
        '''获取用户已点赞的所有ID（批量查询优化）'''
        try:
            members=redis_cache.smembers(cls._user_liked_key(user_id,target_type))
            if not members:
                return set()
            return {
                int(m.decode() if isinstance(m,bytes) else m)
                for m in members
            }
        except Exception as e:
            logger.error(f'获取用户{user_id}点赞列表失败:{e}')
            return set()
        
    @classmethod
    def get_like_count(cls,target_id:int,target_type:str='post'):
        '''获取点赞数量'''
        try:
            return redis_cache.scard(cls._target_likers_key(target_type,target_id)) or 0
        except Exception as e:
            logger.error(f'获取{target_type}:{target_id}点赞数失败:{e}')
            return 0
        
        
        
    @classmethod
    def preload_user_likes(cls,user_id:int,liked_ids:list,target_type:str='post'):
        '''预加载用户点赞状态到redis（批量优化）'''
        if not liked_ids:
            return True
        try:
            key=cls._user_liked_key(user_id,target_type)
            redis_cache.sadd(key,*[str(i) for i in liked_ids ],expire=cls.DEFAULT_EXPIRE)
            return True
        except Exception as e:
            logger.error(f'预加载用户{user_id}点赞状态失败')
            return False

        

