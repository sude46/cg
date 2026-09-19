import json
import logging
import random
import time
from functools import wraps
from typing import Any

from flask import current_app

from utils.redis_util import RedisClient

logger=logging.getLogger(__name__)

class RedisCache:
    '''
    Redis缓存工具类
    - 防穿透：空值缓存(__NULL__)
    - 放雪崩:随机TTL偏移
    - 放击穿:分布式锁缓存加载（cache_through)
    '''
    _instance=None
    def __new__(cls):
        if cls._instance is None:
            cls._instance=super().__new__(cls)
            cls._instance._client=None
        return cls._instance

    #================缓存防护常量===============
    NULL_VALUE='__NULL__'    #空值缓存标记
    NULL_TTL=60              #空值缓存短TTL(秒)
    JITTER_RANGE=(0,60)      #随机偏移范围(放雪崩)

    def _get_client(self, for_write=False):
        '''获取 Redis 连接（支持主从切换）'''
        # 直接透传给 RedisClient，不缓存，确保读写分离生效
        conn = RedisClient.get_conn(for_write=for_write)
        if conn is None:
            logger.error(f"Redis 未连接 (for_write={for_write})")
        return conn

    def get(self,key:str,for_write=False):
        '''获取缓存，命中空值标记是返回None(防穿透)'''

        client = self._get_client(for_write)
        if not client:
            return None
        try:
            data=client.get(key)
            if data==self.NULL_VALUE:
                return None   #放穿透：明确缓存空值
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return data
        except Exception as e:
            logger.error(f'Redis get error:{e}')
            return None

    def set(self,key:str,value:Any,expire:int=300,for_write:bool=True):
        '''
        设置缓存（自动JSON序列化）
        - value=None时缓存空值标记（防穿透）
        - expire增加随机偏移（放雪崩）
        '''
        client = self._get_client(for_write=True)
        if not client:
            return False
        try:
            #放雪崩：随机TTL偏移
            jitter=random.randint(*self.JITTER_RANGE)
            real_expire=expire+jitter

            #防穿透：None缓存为控制标记，使用短TTL
            if value is None:
                value=self.NULL_VALUE
                real_expire=self.NULL_TTL
            if isinstance(value,(dict,list)):
                value=json.dumps(value,ensure_ascii=False)
            return client.setex(key,real_expire,value)
        except Exception as e:
            current_app.logger.error(f'Redis set error:{e}')
            return False

    #=========cache_through(防击穿)
    def cache_through(self,key:str,loader,expire:int=300,for_write:bool=False,lock_timeout:int=10):
        '''
        带分布式锁的缓存加载（防击穿模式）
        流程：
        1.先查缓存，命中直接返回
        2.未命中则尝试获取分布式锁
        3.获得锁的线程回源加载(loader),回填缓存
        4.未获得锁的线程等待后重试
        5.异常时降级为直接回源
        '''
        #先查缓存
        cached=self.get(key,for_write=for_write)
        if cached is not None:
            return cached
        #分布式锁
        lock_key=f'lock:cache:{key}'
        lock_value=str(time.time())

        try:
            #尝试获取锁
            acquired=self.setnx(lock_key,lock_value,expire=lock_timeout)
        except Exception as e:
            logger.error(f'Cache through lock error for key {key}:{e}')
            return loader()

        #未获得锁：等待后递归重试（不得释放他人的锁）
        if not acquired:
            time.sleep(0.1)
            return self.cache_through(key,loader,expire,for_write,lock_timeout)

        try:
            #获得锁后二次检查（防止等待期间已回填)
            cached=self.get(key,for_write=for_write)
            if cached is not None:
                return cached

            #回源加载
            value=loader()
            self.set(key,value,expire=expire)
            return value
        except Exception as e:
            logger.error(f'Cache through error for key {key}:{e}')
            #降级：直接回源。不缓存
            return loader()
        finally:
            #仅持锁路径释放锁
            self.release_lock(lock_key,lock_value)


    def delete(self,key:str):
        '''删除缓存'''
        client = self._get_client(for_write=True)
        if not client:
            return False
        return bool(client.delete(key))
    def increment(self,key:str,amount:int=1):
        '''源自自增（计数器用）'''
        client = self._get_client(for_write=True)
        if not client:
            return 0
        return client.incrby(key,amount)
    def hget(self,key:str,field:str):
        '''Hash获取'''
        client = self._get_client(for_write=False)
        if not client:
            return None
        return client.hget(key,field)
    def hset(self,key:str,field:str,value:str,expire:int=3600):
        '''Hash设置'''
        client = self._get_client(for_write=True)
        if not client:
            return False
        pipe=client.pipeline()
        pipe.hset(key,field,value)
        pipe.expire(key,expire)
        pipe.execute()
        return True
    def hincrby(self,key:str,field:str,amount:int=1):
        '''Hash自增'''
        client = self._get_client(for_write=True)
        if not client:
            return 0
        return client.hincrby(key,field,amount)
    def zadd(self,key:str,mapping:dict[str,float],expire:int=None):
        '''Sorted set添加'''
        client = self._get_client(for_write=True)
        if not client:
            return False
        client.zadd(key,mapping)
        if expire:
            client.expire(key,expire)
        return True
    def zincrby(self,key:str,member:str,amount:int=1):
        '''Sorted set成员分数自增（热搜统计用）'''
        client = self._get_client(for_write=True)
        if not client:
            return 0
        return client.zincrby(key,amount,member)
    def zrevrange(self,key:str,start:int,end:int,withscores=False):
        '''Sorted set倒序获取(feed用)'''
        client = self._get_client(for_write=False)
        if not client:
            return []
        return client.zrevrange(key,start,end,withscores=withscores)
    def zrevrangebyscore(self,key:str,max_score,min_score,start:int=0,num:int=None,withscores:bool=False):
        '''Sorted set按分数倒序获取（feed 游标分页用；只读走副本）'''
        client = self._get_client(for_write=False)
        if not client:
            return []
        return client.zrevrangebyscore(
            key,max_score,min_score,start=start,num=num,withscores=withscores
        )
    def zrem(self,key:str,*members):
        '''Sorted set删除成员'''
        client = self._get_client(for_write=True)
        if not client:
            return 0
        return client.zrem(key,*members)
    def sadd(self,key:str,*members,expire:int=None):
        '''Set添加(关注关系用)'''
        client = self._get_client(for_write=True)
        if not client:
            return False
        client.sadd(key,*members)
        if expire:
            client.expire(key,expire)
        return True
    def sismember(self,key:str,member:str,for_write=False):
        '''Set成员检查（是否已关注/已点赞）'''
        client = self._get_client(for_write=for_write)
        if not client:
            return False
        return client.sismember(key,member)
    def smembers(self,key:str,for_write=False):
        '''Set成员列表（获取粉丝/关注列表）'''
        client = self._get_client(for_write=for_write)
        if not client:
            return set()
        return client.smembers(key)
    def srem(self,key:str,*members):
        '''Set删除成员'''
        client = self._get_client(for_write=True)
        if not client:
            return 0
        return client.srem(key,*members)
    def scard(self,key:str,for_write=False):
        '''Set获取成员数量'''
        client = self._get_client(for_write=for_write)
        if not client:
            return 0
        return client.scard(key)

    def setnx(self,key:str,value:str,expire:int=10):
        '''分布式锁: set if not exists'''
        client = self._get_client(for_write=True)
        if not client:
            return False
        return client.set(key,value,nx=True,ex=expire)
    def release_lock(self,key:str,value:str):
        '''释放分布式锁(Lua脚本保证原子性)'''
        client = self._get_client(for_write=True)
        if not client:
            return False
        lua_script="""
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        return client.eval(lua_script,1,key,value)
    def lpush(self, key: str, *values):
        '''List左侧插入'''
        client = self._get_client(for_write=True)
        if not client:
            return 0
        return client.lpush(key, *values)

    def brpop(self, key: str, timeout: int = 5):
        '''List阻塞右侧弹出（BRPOP 会弹出元素，属写命令，必须走主库）'''
        client = self._get_client(for_write=True)
        if not client:
            return None
        return client.brpop(key, timeout=timeout)

    def expire(self, key: str, seconds: int):
        '''设置过期时间'''
        client = self._get_client(for_write=True)
        if not client:
            return False
        return client.expire(key, seconds)

    def exists(self, *keys: str, for_write: bool = False) -> int:
        """检查 key 是否存在（强一致标记/锁读取请传 for_write=True）"""
        client = self._get_client(for_write=for_write)
        if not client:
            return 0
        return client.exists(*keys)

    def zcard(self, key: str) -> int:
        """ZSet 基数"""
        client = self._get_client(for_write=False)
        if not client:
            return 0
        return client.zcard(key)
    def zremrangebyrank(self, key: str, start: int, end: int) -> int:
        """按排名裁剪 ZSet"""
        client = self._get_client(for_write=True)
        if not client:
            return 0
        return client.zremrangebyrank(key, start, end)

    def pipeline(self, transaction: bool = False,for_write=True):
        """暴露 Pipeline（上层 Cache 类需要批量操作）"""
        client = self._get_client(for_write=for_write)
        if not client:
            raise RuntimeError("Redis client not initialized")
        return client.pipeline(transaction=transaction)

    def eval(self, script: str, numkeys: int, *keys_and_args):
        """暴露 Lua 执行（原子操作需要）"""
        client = self._get_client(for_write=True)
        if not client:
            raise RuntimeError("Redis client not initialized")
        return client.eval(script, numkeys, *keys_and_args)
    def scan_iter(self,match=None,count=None,for_write=False):
        '''迭代器扫描keys（用于清理过期缓存）'''
        client = self._get_client(for_write)
        if not client:
            raise RuntimeError("Redis client not initialized")
        return client.scan_iter(match=match,count=count)

    def script_load(self,script:str):
        '''加载Lua脚本，返回sha1摘要（供evalsha使用）'''
        client=self._get_client(for_write=True)
        if not client:
            raise RuntimeError("Redis client not initialized")
        return client.script_load(script)
    def evalsha(self,sha:str,numkeys:int,*keys_and_args):
        """通过sha执行已加载的Lua脚本（原子操作，比eval省带宽）"""
        client=self._get_client(for_write=True)
        if not client:
            raise RuntimeError("Redis client not initialized")
        return client.evalsha(sha,numkeys,*keys_and_args)


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

