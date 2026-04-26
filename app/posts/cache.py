import logging
from typing import Optional,Dict,Any

from core .redis_cache import redis_cache

logger=logging.getLogger(__name__)

class PostCache:
    '''
    帖子缓存管理
    -String缓存帖子详情(key:post:{id})
    -String缓存计数器(key:counter:post:{id}:like_count)
    '''
    DETAIL_TTL=300   #帖子详情缓存5分钟
    COUNTER_TTL=3600  #计数缓存1小时


    #Lua脚本：原子化递减，保底不小于0
    DECR_LUA='''
    local  current=redis.call('GET',keys[1])
    if current==false or tonumber(current)<=0 then
        redis.call('SET',KEYS[1],0)
        return 0
    end 
    return redis.call('INCRBY',KEYS[1],-1)

    '''

    @classmethod
    def _detail_key(cls,post_id:int):
        return f'post:{post_id}'
    
    @classmethod
    def _counter_key(cls,post_id,field:str):
        return f'counter:post:{post_id}:{field}'
    
    #============帖子详情缓存（String）==============
    @classmethod
    def get(cls,post_id:int):
        '''
        获取帖子详情缓存
        注意：redis_cache.get内部已经做了json.loads,
        如果存的是dict,直接返回dict
        '''
        try:
            return redis_cache.get(cls._detail_key(post_id))
        except Exception as e:
            logger.error(f'获取帖子{post_id}缓存失败:{e}')
            return None
        
    
    @classmethod
    def set(cls,post_id:int,post_data:Dict[str,Any]):
        '''缓存帖子详情(自动Json序列化)'''
        try:
            return redis_cache.set(cls._detail_key(post_id),post_data,expire=cls.DETAIL_TTL)
        except Exception as e:
            logger.error(f'设置帖子{post_id}缓存失败:{e}')
            return False
    @classmethod
    def invalidate(cls,post_id:int):
        '''删除帖子详情缓存'''
        try:
            return redis_cache.delete(cls._detail_key(post_id))
        except Exception as e:
            logger.error(f'删除帖子{post_id}缓存失败:{e}')
            return False
        
    
    #================计数器缓存=======================
    @classmethod
    def get_like_count(cls,post_id:int):
        '''获取Redis中的点赞数'''
        try:
            val=redis_cache.get(cls._counter_key(post_id,'like_count'))
            if val is None:
                return None
            return int(val) if not isinstance(val,int) else val
        except Exception as e:
            logger.error(f'获取帖子{post_id}点赞数失败:{e}')
            return None
        
    
    @classmethod
    def set_like_count(cls,post_id:int,count:int):
        '''设置点赞数缓存（回源数据库后调用)'''
        try:
            return redis_cache.set(cls._counter_key(post_id,'like_count'),count,expire=cls.COUNTER_TTL)
        except Exception as e:
            logger.error(f'设置帖子{post_id}点赞数失败:{e}')
            return False
        
    
    @classmethod
    def increment_like_count(cls,post_id:int):
        '''点赞数+1（原子自增）'''
        try:
            return redis_cache.increment(cls._counter_key(post_id,'like_count'),1)
        except Exception as e:
            logger.error(f'递增帖子{post_id}点赞数失败:{e}')
            return 0
        
    @classmethod
    def decrement_like_count(cls,post_id:int):
        '''
        点赞数-1（原子操作，保底不小于）
        说明：redis_cache.increment支持负数，这里先做边界兜底
        '''
        try:
            key=cls._counter_key(post_id,'like_count')
            result=redis_cache.client.eval(cls.DECR_LUA,1,key)
            return int(result)
        except Exception as e:
            logger.error(f'递减帖子{post_id}点赞数失败:{e}')
            return 0
    
    @classmethod
    def delete_like_count(cls,post_id:int):
        '''删除点赞计数缓存'''
        try:
            return redis_cache.delete(cls._counter_key(post_id,'like_count'))
        except Exception as e:
            logger.error(f'删除帖子{post_id}点赞计数失败:{e}')
            return False
    
    @classmethod
    def invalidate_all(cls,post_id):
        '''帖子变更时:清详情缓存+清计数缓存'''
        try:
            pipe=redis_cache.pipeline(transaction=False)
            pipe.delete(cls._detail_key(post_id))
            pipe.delete(cls._counter_key(post_id,'like_count'))
            pipe.execute()
        except Exception as e:
            logger.error(f'清楚帖子{post_id}全部缓存失败:{e}')


    