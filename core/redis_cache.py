import json
import pickle
from typing import Any,Optional,Union,List,Dict
from functools import wraps
from datetime import timedelta
from flask import current_app
from config import get_config

class RedisCache:
    '''
    Redis缓存工具类
    为Post/Likes/Feed等业务层提供统一封装
    '''
    _instance=None
    def __new__(cls):
        if cls._instance is None:
            cls._instance=super().__new__(cls)
            cls._instance._client=None
        return cls._instance
    @property
    def client(self):
        '''获取Redis客户端(从Flask app.config或新建)'''
        if self._client is None:
            #优先从当前Flask应用获取（已初始化））
            try:
                self._client=current_app.config.get('REDIS_CLIENT')
            except RuntimeError:
                pass
            #如果没有，直接按从配置创建
            if self._client is None:
                config_class=get_config()
                self._client=config_class.get_redis_client()
        return self._client
    def get(self,key:str):
        '''获取缓存（走动反序列化JSON）'''
        if not self.client:
            return None
        data=self.client.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
        return None
    def set(self,key:str,value:Any,expire:int=300):
        '''设置缓存（自动JSON序列化）'''
        if not self.client:
            return False
        try:
            if isinstance(value,(dict,list)):
                value=json.dumps(value,ensure_ascii=False)
            return self.client.setex(key,expire,value)
        except Exception as e:
            current_app.logger.error(f'Redis set error:{e}')
            return False
    def delete(self,key:str):
        '''删除缓存'''
        if not self.client:
            return False
        return bool(self.client.delete(key))
    def increment(self,key:str,amount:int=1):
        '''源自自增（计数器用）'''
        if not self.client:
            return 0
        return self.client.incrby(key,amount)
    def hget(self,key:str,field:str):
        '''Hash获取'''
        if not self.client:
            return None
        return self.client.hget(key,field)
    def hset(self,key:str,field:str,value:str,expire:int=3600):
        '''Hash设置'''
        if not self.client:
            return False
        pipe=self.client.pipeline()
        pipe.hset(key,field,value)
        pipe.expire(key,expire)
        pipe.execute()
        return True
    def hincrby(self,key:str,field:str,amount:int=1):
        '''Hash自增'''
        if not self.client:
            return 0
        return self.client.hincrby(key,field,amount)
    def zadd(self,key:str,mapping:Dict[str,float],expire:int=None):
        '''Sorted set添加'''
        if not self.client:
            return False
        self.client.zadd(key,mapping)
        if expire:
            self.client.expire(key,expire)
        return True
    def zrevrange(self,key:str,start:int,end:int,withscores=False):
        '''Sorted set倒序获取(feed用)'''
        if not self.client:
            return []
        return self.client.zrevrange(key,start,end,withscores=withscores)
    def zrem(self,key:str,*members):
        '''Sorted set删除成员'''
        if not self.client:
            return 0
        return self.client.zrem(key,*members)
    def sadd(self,key:str,*members,expire:int=None):
        '''Set添加(关注关系用)'''
        if not self.client:
            return False
        self.client.sadd(key,*members)
        if expire:
            self.client.expire(key,expire)
        return True
    def sismember(self,key:str,member:str):
        '''Set成员检查（是否已关注/已点赞）'''
        if not self.client:
            return False
        return self.client.sismember(key,member)
    def smembers(self,key:str):
        '''Set成员列表（获取粉丝/关注列表）'''
        if not self.client:
            return set()
        return self.client.smembers(key)
    def srem(self,key:str,*members):
        '''Set删除成员'''
        if not self.client:
            return 0
        return self.client.srem(key,*members)
    def scard(self,key:str):
        '''Set获取成员数量'''
        if not self.client:
            return 0
        return self.client.scard(key)
    
    def setnx(self,key:str,value:str,expire:int=10):
        '''分布式锁: set if not exists'''
        if not self.client:
            return False
        return self.client.set(key,value,nx=True,ex=expire)
    def release_lock(self,key:str,value:str):
        '''释放分布式锁(Lua脚本保证原子性)'''
        if not self.client:
            return False
        lua_script="""
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        return self.client.eval(lua_script,1,key,value)
    def lpush(self, key: str, *values):
        '''List左侧插入'''
        if not self.client:
            return 0
        return self.client.lpush(key, *values)

    def brpop(self, key: str, timeout: int = 5):
        '''List阻塞右侧弹出'''
        if not self.client:
            return None
        return self.client.brpop(key, timeout=timeout)

    def expire(self, key: str, seconds: int):
        '''设置过期时间'''
        if not self.client:
            return False
        return self.client.expire(key, seconds)
    
    def exists(self, *keys: str) -> int:
        """检查 key 是否存在"""
        if not self.client:
            return 0
        return self.client.exists(*keys)

    def zcard(self, key: str) -> int:
        """ZSet 基数"""
        if not self.client:
            return 0
        return self.client.zcard(key)

    def zremrangebyrank(self, key: str, start: int, end: int) -> int:
        """按排名裁剪 ZSet"""
        if not self.client:
            return 0
        return self.client.zremrangebyrank(key, start, end)

    def pipeline(self, transaction: bool = False):
        """暴露 Pipeline（上层 Cache 类需要批量操作）"""
        if not self.client:
            raise RuntimeError("Redis client not initialized")
        return self.client.pipeline(transaction=transaction)

    def eval(self, script: str, numkeys: int, *keys_and_args):
        """暴露 Lua 执行（原子操作需要）"""
        if not self.client:
            raise RuntimeError("Redis client not initialized")
        return self.client.eval(script, numkeys, *keys_and_args)

    
redis_cache=RedisCache()

def cache(key_prefix:str,expire:int=300):
    '''装饰器：缓存函数结果
    用法：@cache(key_prefix='post',expire=300 )
    '''
    def decorator(f):
        @wraps(f)
        def decorated_function(*args,**kwargs):
            #生成缓存key:prefix:arg1:arg2
            cache_key=f"{key_prefix}:{':'.join(str(a) for a in args)}"
            #尝试获取缓存
            cached_value=redis_cache.get(cache_key)
            if cached_value is not None :
                return cached_value
            #执行原函数
            result=f(*args,**kwargs)
            if result:
                redis_cache.set(cache_key,result,expire)
            return result 
        return decorated_function
    return decorator

