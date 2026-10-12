import logging
import math
import threading
import time
from datetime import UTC, datetime
from typing import Any

from core.metrics import READ_FORCED_MASTER, RECENT_MODIFY_MARKED
from core.redis_cache import redis_cache

logger = logging.getLogger(__name__)


class PostCache:
    """
    帖子缓存管理（只缓存帖子自身数据）
    -只缓存帖子自身详情: post:detail:{id}
    - 支持延迟双删+强一致标记（recent_modify)
    """
    DETAIL_TTL = 300  # 5 分钟
    RECENT_MODIFY_TTL=60   #强一致窗口5秒

    @classmethod
    def _detail_key(cls, post_id: int) -> str:
        return f'post:detail:{post_id}'

    @classmethod
    def _recent_key(cls,post_id:int):
        return f'post:recent_modify:{post_id}'


    @classmethod
    def get(cls, post_id: int) -> dict[str, Any] | None:
        """读帖子详情（从库）"""
        try:
            return redis_cache.get(cls._detail_key(post_id), for_write=False)
        except Exception as e:
            logger.error(f'获取帖子{post_id}缓存失败: {e}')
            return None

    @classmethod
    def set(cls, post_id: int, post_data: dict[str, Any]) -> bool:
        """写帖子详情（主库）"""
        try:
            return redis_cache.set(
                cls._detail_key(post_id), post_data,
                expire=cls.DETAIL_TTL, for_write=True
            )
        except Exception as e:
            logger.error(f'设置帖子{post_id}缓存失败: {e}')
            return False

    @classmethod
    def invalidate(cls, post_id: int) -> bool:
        """删帖子详情（主库）。不删 recent_modify 标记：该标记由 TTL 自然过期，
        若在此删除会让延迟双删的第二次删除（delayed_invalidate）提前结束强一致窗口。"""
        try:
            key = cls._detail_key(post_id)
            return redis_cache.delete(key)
        except Exception as e:
            logger.error(f'删除帖子{post_id}缓存失败: {e}')
            return False

    @classmethod
    def double_invalidate(cls, post_id: int) -> None:
        """延迟双删（update/delete 后调）"""
        cls.invalidate(post_id)
        def _delayed():
            time.sleep(1.5)
            cls.invalidate(post_id)
        threading.Thread(target=_delayed, daemon=True).start()

    #=============强一致标记(创建/更新/删除后使用)===============
    @classmethod
    def mark_recently_modified(cls,post_id:int,ttl:int=None):
        '''
        标记帖子最近被修改，后续读强制走主库（防主从延迟）
        TTL默认5秒
        '''
        ttl=ttl or cls.RECENT_MODIFY_TTL
        key=cls._recent_key(post_id)
        try:
            ok = redis_cache.set(key,"1",expire=ttl,for_write=True)
            if ok:
                RECENT_MODIFY_MARKED.labels(resource='post').inc()
            return ok
        except Exception as e:
            logger.error(f'标记帖子{post_id}最近修改失败:{e}')
            return False

    @classmethod
    def is_recently_modified(cls,post_id:int):
        """检查帖子是否在强一致窗口内"""
        key=cls._recent_key(post_id)
        try:
            hit = redis_cache.exists(key, for_write=True)>0
            if hit:
                READ_FORCED_MASTER.labels(resource='post').inc()
            return hit
        except Exception as e:
            logger.error(f'检查帖子{post_id}最近修改失败:{e}')
            return False

    #================热帖===================
    HOT_DAILY_KEY='hot:posts:daily'
    HOT_TTL=86400*2
    HOT_SCORE_MULTIPLIER=1_000_000      #浮点转整数 ，把保留6位小数精度

    @classmethod
    def calc_hot_score(cls,like_count:int,comment_count:int,created_at:datetime):
        '''
        热度分计算(整数版，避免Redis Zset double 精度问题)
        公式:(likes*2+comments*3)/(hours+2)^1.5*1_000_000
        '''
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        hours=max(0,(datetime.now(UTC)-created_at).total_seconds()/3600)
        interaction=like_count*2+comment_count*3
        score_float=interaction/math.pow(hours+2,1.5)
        return int(score_float*cls.HOT_SCORE_MULTIPLIER)


    @classmethod
    def update_hot_posts(cls,posts_data:list[dict],period:str='daily'):
        '''
        重建热帖榜（定时任务调用）：先清空再写，避免已删/超出时间窗的帖子残留。
        posts_data:[{'post_id':1,'score':12345556},......]；空列表表示本次无热帖。
        '''

        try:
            key=f'hot:posts:{period}'
            pipe=redis_cache.pipeline(transaction=False,for_write=True)

            #先清空，保证榜单与本次计算结果一致
            pipe.delete(key)
            if posts_data:
                #使用整数score
                mapping={str(p['post_id']):p['score'] for p in posts_data}
                pipe.zadd(key,mapping)
                pipe.zremrangebyrank(key,0,-1001)      #只预留top1000
                pipe.expire(key,cls.HOT_TTL)
            pipe.execute()

            logger.info(f'[HotPosts]更新{period}榜，共{len(posts_data)}条')
            return True
        except Exception:
            logger.error('[HotPost]更新失败')
            return False

    @classmethod
    def get_hot_posts(cls,page:int=1,per_page:int=20,period:str='daily'):
        try:
            key=f'hot:posts:{period}'
            start=(page-1)*per_page
            end=start+per_page-1

            results=redis_cache.zrevrange(key,start,end,withscores=False)
            total=redis_cache.zcard(key) or 0

            if not results:
                return [],0
            post_ids=[int(r.decode() if isinstance(r,bytes)else r) for r in results]
            return post_ids,total
        except Exception as e:
            logger.error(f'[HotPosts]获取失败：{e}')
            return [],0




