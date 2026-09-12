import logging
import threading
import time
from typing import Any

from core.redis_cache import redis_cache

logger=logging.getLogger(__name__)

class CommentCache:
    '''
    评论缓存管理
    -评论详情：comment:detail:{id}{String/JSON}---Cache-Aside+延迟双删
    -帖子评论计数：post:{id}:comment_count(String)-原子Invr/Decr

    注意：
    - 点赞状态归 likes/ 管
    - 帖子详情归 posts/ 管，posts/ 只读本计数器

    '''
    DETAIL_TTL=300  #5分钟
    COUNT_TTL=3600  #1小时



    #LUA：原子递减，保底不小于0
    DECR_LUA="""
    local current=redis.call('GET', KEYS[1])
    if current==false or tonumber(current)<=0 then
        redis.call('SET',KEYS[1],0)
        return 0
    end
    return redis.call('DECRBY',KEYS[1],1)
    """

    @classmethod
    def _detail_key(cla,comment_id:int):
        return f"comment:detail:{comment_id}"

    @classmethod
    def _count_key(cls,post_id:int):
        '''帖子评论数Key(被posts/services.py读取)'''
        return f'post:{post_id}:comment_count'



    #========评论详情缓存（主从分离）=============

    @classmethod
    def get(cls,comment_id:int):
        '''读评论详情(Redis从库)'''
        try:
            return  redis_cache.get(cls._detail_key(comment_id),for_write=False)
        except Exception:
            logger.error(f'读评论{comment_id}详情失败')
            return None

    @classmethod
    def set(cls,comment_id:int,comment_data:dict[str,Any]):
        '''写评论详情(Redis主库)'''
        try:
            return redis_cache.set(
                cls._detail_key(comment_id),
                comment_data,
                expire=cls.DETAIL_TTL,for_write=True
            )
        except Exception as e:
            logger.error(f'设置评论{comment_id}缓存失败:{e}')
            return False


    @classmethod
    def invalidate(cls,comment_id:int):
        '''删评论详情(Redis主库)'''
        try:
            return redis_cache.delete(cls._detail_key(comment_id))
        except Exception as e:
            logger.error(f'删除评论{comment_id}缓存失败:{e}')
            return False

    @classmethod
    def double_invalidate(cls,comment_id:int):
        '''延迟双删：立即删+1.5秒后二次删'''
        cls.invalidate(comment_id)
        def _delayed():
            time.sleep(1.5)
            cls.invalidate(comment_id)
        threading.Thread(target=_delayed,daemon=True).start()


    #==================帖子评论计数====================
    @classmethod
    def get_count(cls,post_id:int):
        '''读帖子评论数(Redis从库)'''
        try:
            val=redis_cache.get(cls._count_key(post_id),for_write=False)
            return int(val) if val is not None else None
        except Exception as e:
            logger.error(f'获取帖子{post_id}评论数失败:{e}')
            return False


    @classmethod
    def set_count(cls,post_id:int,count:int):
        '''设置评论数(回填用，Redis主库)'''
        try:
            return redis_cache.set(
                cls._count_key(post_id),count,
                expire=cls.COUNT_TTL,for_write=True
            )
        except Exception as e:
            logger.error(f'设置帖子{post_id}评论数失败:{e}')
            return False

    @classmethod
    def increment_count(cls,post_id):
        try:
            return redis_cache.increment(cls._count_key(post_id),1)
        except Exception as e:
            logger.error(f'递增帖子{post_id}评论失败:{e}')
            return 0

    @classmethod
    def decrement_count(cls,post_id):
        try:
            result=redis_cache.eval(cls.DECR_LUA,1,cls._count_key(post_id))
            return int(result) if result else 0
        except Exception as e:
            logger.error(f'递减帖子{post_id}评论数失败:{e}')
            return  0

    #=============热评榜Zet=======
    HOT_COMMENTS_PRE_POST=100
    HOT_COMMENTS_TTL=86400*3

    @classmethod
    def _hot_key(cls,post_id:int):
        return f'post:{post_id}:hot_comments'

    @classmethod
    def update_hot_comment(cls,post_id:int,comment_id:int,like_count:int):
        '''
        实时更新热评榜(评论被点赞是调用)
        like_count为0时从榜单移除
        '''
        try:
            key=cls._hot_key(post_id)
            if like_count<=0:
                redis_cache.zrem(key,str(comment_id))
                return True

            pipe=redis_cache.pipeline(transaction=False,for_write=True)
            pipe.zadd(key,{str(comment_id):like_count})
            pipe.zremrangebyrank(key,0,-(cls.HOT_COMMENTS_PRE_POST+1))
            pipe.expire(key,cls.HOT_COMMENTS_TTL)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'[HotComments] 更新热评失败 post={post_id} comment={comment_id}: {e}')
            return False

    @classmethod
    def get_hot_comments(cls,post_id:int,page:int=1,per_page:int=20):
        '''
        获取热评评论Id列表
        返回:{comment_ids_list,total}
        '''
        try:
            key=cls._hot_key(post_id)
            start=(page-1)*per_page
            end=start+per_page-1

            results=redis_cache.zrevrange(key,start,end,withscores=False)
            total=redis_cache.zcard(key) or 0

            if not results:
                return [] ,0

            comment_ids=[int(r.decode() if isinstance(r,bytes) else r) for r in results]
            return comment_ids,total
        except Exception as e:
            logger.error(f'[HotComments]获取热评失败post={post_id}:{e}')
            return [],0

    @classmethod
    def rebuild_hot_comments(cls,post_id:int,comments_data):
        '''
        定时兜底：从DB全量重建某贴的热评ZSet,
        comments_data: [{'comment_id': 1, 'like_count': 50}, ...]
        '''
        try:
            key=cls._hot_key(post_id)
            if not comments_data:
                redis_cache.delete(key)
                return key
            pipe=redis_cache.pipeline(transaction=False,for_write=True)
            #先清空再重建（避免残留已删除的评论）
            pipe.delete(key)
            mapping={str(c['comment_id']):c['like_count'] for c in comments_data}
            pipe.zadd(key,mapping)
            pipe.zremrangebyrank(key,0,-(cls.HOT_COMMENTS_PRE_POST+1))
            pipe.expire(key,cls.HOT_COMMENTS_TTL)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'[HotComments]重建热评失败post={post_id}:{e}')
            return False








