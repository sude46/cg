'''
Feed流Redis缓存
推模式：大V发贴时，主动推送到所有粉丝的Feed流
拉模式：普通用户打开首页时，实时拉去关注对象的最新贴子
'''
import logging
from datetime import UTC, datetime

from config import get_config
from core.redis_cache import redis_cache

from .cursor import encode_cursor
from .cursor import score_for as _score

_BIG_V_THRESHOLD=get_config()().BIG_V_THRESHOLD



logger=logging.getLogger(__name__)

def _to_timestamp(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()

class FeedCache:
    '''
    用户时间线缓存

    数据结构:Sorted Set
    -key:feed:user:{uid}
    -score:帖子创建时间戳(保证时序)
    -member:帖子ID
    '''

    #配置常量(便于集中管理和动态调整)
    MAX_FEED_SIZE=500 #每个用户时间线保留的最大贴子数
    FEED_EXPIRE_DAYS=7  #缓存过期天数
    EMPTY_CACHE_TTL=60   #空缓存防穿透过期时间(秒)
    PUSH_BATCH_SIZE=1000   #推模式分批大小(避免Ppeline过大阻塞Redis)
    MAX_AUTHOR_OUTBOX=500  #每个作者 outbox 保留的最大帖子数(拉模式数据源)
    MAX_MERGE_BIGV=50      #读时参与K路归并的大V上限,超过则退化为DB兜底
    BIGV_SET_KEY='feed:bigv'    #大V作者集合，发帖时自动维护

    @classmethod
    def _feed_key(cls,user_id:int):
        return f'feed:user:{user_id}'
    @classmethod
    def _empty_key(cls,user_id:int):
        '''空缓存标记键，用于防缓存穿透'''
        return f'feed:user:{user_id}:empty'
    @classmethod
    def _author_key(cls,author_id:int):
        '''作者 outbox: 该作者最近发布的帖子(拉模式读取源)'''
        return f'feed:author:{author_id}'

    @classmethod
    def threshold(cls) -> int:
        '''大V阈值:优先取运行时配置,无 app 上下文时回退到导入期值'''
        try:
            from flask import current_app
            value=current_app.config.get('BIG_V_THRESHOLD')
            if value is not None:
                return int(value)
        except Exception:
            pass
        return _BIG_V_THRESHOLD

    @classmethod
    def is_big_v(cls, follower_count: int) -> bool:
        return follower_count >= cls.threshold()

    @classmethod
    def fanout_async_threshold(cls) -> int:
        '''fanout 异步阈值:粉丝>=该值走 Celery 异步推送,以下同步推送'''
        try:
            from flask import current_app
            value=current_app.config.get('FEED_FANOUT_ASYNC_THRESHOLD')
            if value is not None:
                return int(value)
        except Exception:
            pass
        return 500

    @classmethod
    def push_to_followers(cls,post_id:int,created_at:float,follower_ids:list[int],follower_count=None):
        '''
        推模式：帖子创建后，推送到所有粉丝的时间线
        Args:
        post_id:帖子ID
        created_at:帖子创建时间（float时间戳或datetime对象）
        follower_ids:粉丝列表
        follower_count:粉丝总数(用于大V判断，默认取len(follower_idsfollower_ids))
        returns:
            dict :推送结果

        '''
        #统一时间戳格式
        if isinstance(created_at,datetime):
            created_at=_to_timestamp(created_at)
        #大v判断：粉丝过多时不推，避免写入爆炸
        actual_count=follower_count if follower_count is not None else len(follower_ids)

        if cls.is_big_v(actual_count):
            logger.info(f'帖子{post_id}作者为大V（{actual_count}粉丝），跳过推送，使用拉模式')
            return{
                'post_id':post_id,
                'pushed':0,
                'mode':'pull',
                'reason':'big_v_threshold'
            }
        total_pushed = 0
        expire_seconds = cls.FEED_EXPIRE_DAYS * 86400
        try:
            # 必须分批 Pipeline！10 万粉丝一次发过去会阻塞 Redis 数秒
            for i in range(0, len(follower_ids), cls.PUSH_BATCH_SIZE):
                batch = follower_ids[i:i + cls.PUSH_BATCH_SIZE]
                pipe = redis_cache.pipeline(transaction=False,for_write=True)

                for fid in batch:
                    key = cls._feed_key(fid)
                    pipe.zadd(key, {str(post_id): _score(int(created_at), int(post_id))})
                    # 保留最近 MAX_FEED_SIZE 条，超出裁剪
                    pipe.zremrangebyrank(key, 0, -(cls.MAX_FEED_SIZE + 1))
                    pipe.expire(key, expire_seconds)
                    # 新帖子来了，清除该粉丝的空缓存标记
                    pipe.delete(cls._empty_key(fid))

                pipe.execute()
                total_pushed += len(batch)

            logger.info(f"帖子{post_id}已推送到{total_pushed}个粉丝的时间线，模式：push")
            return {
                "post_id": post_id,
                "pushed": total_pushed,
                "mode": "push",
                "follower_count": actual_count
            }
        except Exception as e:
            logger.error(f"推送帖子{post_id}到粉丝时间线失败: {e}")
            raise


    @classmethod
    def pull_feed(cls,user_id:int,page:int=1,per_page:int=20):
        '''
        拉模式：从Redis获取用户的时间线帖子ID列表
        Args:
            user_id:用户Id
            page:页码（从1开始）
            per_page:每页条数
        Returns:
            List[str]:帖子Id列表（缓存命中且有数据）
            []:空列表（缓存命中但无数据，用户可能未关注任何人）
            None：缓存未命中（需要走数据库）
        '''
        key = cls._feed_key(user_id)
        empty_key = cls._empty_key(user_id)

        try:
            # 现有封装没有 exists，直接访问原生 client
            if redis_cache.exists(empty_key):
                return []

            if not redis_cache.exists(key):
                return None

            start = (page - 1) * per_page
            end = start + per_page - 1
            post_ids = redis_cache.zrevrange(key, start, end)

            return [
                pid.decode() if isinstance(pid, bytes) else str(pid)
                for pid in post_ids
            ]
        except Exception as e:
            logger.error(f"拉取用户{user_id}时间线失败: {e}")
            return None

    @classmethod
    def pull_feed_by_cursor(cls,user_id:int,cursor,limit:int=20):
        '''
        游标拉取时间线（Redis ZSet，按 score 倒序）。
        cursor: (sec, post_id) 元组或 None（首页）
        返回 (post_ids, next_cursor, has_more)；None 表示缓存未命中需走 DB。
        '''
        key = cls._feed_key(user_id)
        empty_key = cls._empty_key(user_id)
        try:
            if redis_cache.exists(empty_key):
                return [], None, False
            if not redis_cache.exists(key):
                return None

            if cursor is None:
                max_score = '+inf'
            else:
                score, _pid = cursor
                max_score = f'({float(score)}'  # 开区间，排除上一页最后一条

            rows = redis_cache.zrevrangebyscore(
                key, max_score, '-inf', start=0, num=limit + 1, withscores=True
            )
            has_more = len(rows) > limit
            rows = rows[:limit]
            if not rows:
                return [], None, False

            post_ids = [
                (m.decode() if isinstance(m, bytes) else str(m)) for m, _ in rows
            ]
            next_cursor = (
                encode_cursor(rows[-1][1], rows[-1][0]) if has_more else None
            )
            return post_ids, next_cursor, has_more
        except Exception as e:
            logger.error(f"游标拉取用户{user_id}时间线失败: {e}")
            return None

    @classmethod
    def pull_feed_scored_by_cursor(cls,user_id:int,cursor,limit:int=20):
        '''
        与 pull_feed_by_cursor 同语义,但返回带 score 的 [(member, score), ...],
        供"推来的feed + 关注的大V outbox"多源归并排序使用。
        返回 None：缓存未命中(需走DB)；[]：空缓存标记；否则为候选列表(最多 limit+1 条)
        '''
        key = cls._feed_key(user_id)
        empty_key = cls._empty_key(user_id)
        try:
            if redis_cache.exists(empty_key):
                return []
            if not redis_cache.exists(key):
                return None
            max_score='+inf' if cursor is None else f'({float(cursor[0])}'
            rows=redis_cache.zrevrangebyscore(
                key,max_score,'-inf',start=0,num=limit+1,withscores=True
            )
            return [
                (m.decode() if isinstance(m,bytes) else str(m),float(s))
                for m,s in rows
            ]
        except Exception as e:
            logger.error(f"游标拉取用户{user_id}时间线(带score)失败: {e}")
            return None

    @classmethod
    def add_to_outbox(cls,author_id:int,post_id:int,created_at:float)->bool:
        '''作者 outbox: 每个作者发帖都写一份(只写1次,与粉丝数无关),拉模式读取源'''
        if isinstance(created_at,datetime):
            created_at=_to_timestamp(created_at)
        try:
            key=cls._author_key(author_id)
            pipe=redis_cache.pipeline(transaction=False,for_write=True)
            pipe.zadd(key,{str(post_id):_score(int(created_at),int(post_id))})
            pipe.zremrangebyrank(key,0,-(cls.MAX_AUTHOR_OUTBOX+1))
            pipe.expire(key,cls.FEED_EXPIRE_DAYS*86400)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'写入作者{author_id} outbox失败 post_id={post_id}:{e}')
            return False

    @classmethod
    def remove_from_outbox(cls,author_id:int,post_id:int)->bool:
        '''删帖时从作者 outbox 移除'''
        try:
            return bool(redis_cache.zrem(cls._author_key(author_id),str(post_id)))
        except Exception as e:
            logger.error(f'从作者{author_id} outbox移除帖子{post_id}失败:{e}')
            return False

    @classmethod
    def pull_outbox_scored_by_cursor(cls,author_id:int,cursor,limit:int=20):
        '''
        按游标读取作者 outbox,返回 [(member, score), ...] (最多 limit+1 条)。
        outbox 不存在时返回 [] (没有可拉的帖,不视为缓存未命中)。
        '''
        key=cls._author_key(author_id)
        try:
            if not redis_cache.exists(key):
                return []
            max_score='+inf' if cursor is None else f'({float(cursor[0])}'
            rows=redis_cache.zrevrangebyscore(
                key,max_score,'-inf',start=0,num=limit+1,withscores=True
            )
            return [
                (m.decode() if isinstance(m,bytes) else str(m),float(s))
                for m,s in rows
            ]
        except Exception as e:
            logger.error(f'拉取作者{author_id} outbox失败:{e}')
            return []

    @classmethod
    def add_post_to_feed(cls,user_id:int,post_id:int,created_at:float):
        '''用户自己发帖也加入自己时间线'''
        if isinstance(created_at,datetime):
            created_at=_to_timestamp(created_at)
        try:
            key = cls._feed_key(user_id)
            pipe = redis_cache.pipeline(transaction=False,for_write=True)
            pipe.zadd(key, {str(post_id): _score(int(created_at), int(post_id))})
            pipe.zremrangebyrank(key, 0, -(cls.MAX_FEED_SIZE + 1))
            pipe.expire(key, cls.FEED_EXPIRE_DAYS * 86400)
            pipe.delete(cls._empty_key(user_id))
            pipe.execute()

            logger.debug(f"帖子{post_id}已加入用户{user_id}自己的时间线")
            return True
        except Exception as e:
            logger.error(f"添加帖子{post_id}到用户{user_id}时间线失败: {e}")
            return False

    @classmethod
    def remove_posts(cls,user_id:int,post_id:int):
        '''从单个用户的时间线中移除帖子（用户自己删除或取关等场景'''
        try:
            result = redis_cache.zrem(cls._feed_key(user_id), str(post_id))
            if result:
                logger.debug(f"帖子{post_id}已从用户{user_id}的时间线移除")
            return bool(result)
        except Exception as e:
            logger.error(f"从用户{user_id}时间线移除帖子{post_id}失败: {e}")
            return False

    @classmethod
    def remove_post_from_all_followers(cls,post_id:int,follower_ids:list[int]):
        '''
        帖子删除时，从所有粉丝的时间线中移除
        **重要**:此操作可能较重，建议通过Celery/RQ异步执行
        '''
        if not follower_ids:
            return {'post_id':post_id,'removed_from':0}
        removed_count = 0

        try:
            for i in range(0, len(follower_ids), cls.PUSH_BATCH_SIZE):
                batch = follower_ids[i:i + cls.PUSH_BATCH_SIZE]
                pipe = redis_cache.pipeline(transaction=False,for_write=True)

                for fid in batch:
                    pipe.zrem(cls._feed_key(fid), str(post_id))

                results = pipe.execute()
                removed_count += sum(1 for r in results if r)

            logger.info(
                f"帖子{post_id}已从{removed_count}/{len(follower_ids)}个粉丝时间线移除"
            )
            return {
                "post_id": post_id,
                "removed_from": removed_count,
                "total_followers": len(follower_ids)
            }
        except Exception as e:
            logger.error(f"从粉丝时间线移除帖子{post_id}失败: {e}")
            return {"post_id": post_id, "removed_from": 0, "error": str(e)}

    @classmethod
    def set_empty_cache(cls,user_id:int):
        '''
        设置空缓存标记（防缓存穿透）
        当用户确实没有关注任何人，或时间线为空时调用
        '''
        try:
            # redis_cache.set 对字符串直接 setex，不会额外 json.dumps
            redis_cache.set(cls._empty_key(user_id), "1", expire=cls.EMPTY_CACHE_TTL)
            logger.debug(f"用户{user_id}设置空缓存标记，TTL={cls.EMPTY_CACHE_TTL}s")
            return True
        except Exception as e:
            logger.error(f"设置用户{user_id}空缓存标记失败: {e}")
            return False

    @classmethod
    def invalidate_feed(cls,user_id:int):
        '''
        清楚用户时间线缓存（用户取关/关注时调用
        同时清除空缓存标记
        '''
        try:
            pipe = redis_cache.pipeline(transaction=False,for_write=True)
            pipe.delete(cls._feed_key(user_id))
            pipe.delete(cls._empty_key(user_id))
            pipe.execute()

            logger.info(f"用户{user_id}的时间线缓存已清除")
            return True
        except Exception as e:
            logger.error(f"清除用户{user_id}时间线缓存失败: {e}")
            return False

    @classmethod
    def mark_big_v(cls,author_id:int)->None:
        """大V发帖时登记(幂等)"""
        try:
            redis_cache.sadd(cls.BIGV_SET_KEY,str(author_id))
        except Exception as e:
            logger.error(f"登记大V失败{author_id}:{e}")

    @classmethod
    def unmark_big_v(cls,author_id:int)->None:
        """粉丝掉回阈值以下时取消登记(幂等)"""
        try:
            redis_cache.srem(cls.BIGV_SET_KEY,str(author_id))
        except Exception as e:
            logger.error(f"取消登记大V失败{author_id}:{e}")

    @classmethod
    def filter_big_v(cls,author_ids:list[int])->list[int]:
        """从关注列表里筛出大V(pipeline批量SISMEMBER),顺序保留"""
        if not author_ids:
            return []
        try:
            pipe=redis_cache.pipeline(transaction=False,for_write=False)
            for aid in author_ids:
                pipe.sismember(cls.BIGV_SET_KEY,str(aid))
            flags=pipe.execute()
            return [aid for aid,ok in zip(author_ids,flags) if ok]
        except Exception as e:
            logger.error(f"筛选大V关注失败:{e}")
            return []

    @classmethod
    def followed_any_big_v(cls,author_ids:list[int])->bool:
        """用户关注的人里有没有大V(pipeline批量SISMEMBER)"""
        return bool(cls.filter_big_v(author_ids))


    @classmethod
    def batch_fill_cache(cls,user_id:int,posts:list[dict],expire:int=None):
        '''
        批量填充用户时间线缓存（数据库查询后回填）
        Args:
            user_id: 用户ID
            posts: 帖子列表，每个帖子需包含id和created_at字段
                  例如：[{'id': 1, 'created_at': 1699123456.0}, ...]
        '''
        if not posts:
            #没有帖子，设置空缓存标记放穿透
            cls.set_empty_cache(user_id)
            return True
        try:
            key = cls._feed_key(user_id)
            mapping = {}
            for post in posts:
                pid = str(post["id"])
                ts = _to_timestamp(post["created_at"])
                mapping[pid] = _score(int(ts), int(pid))

            # 用 Pipeline 保证原子性
            pipe = redis_cache.pipeline(transaction=False,for_write=True)
            pipe.zadd(key, mapping)
            pipe.zremrangebyrank(key, 0, -(cls.MAX_FEED_SIZE + 1))
            pipe.expire(key,expire or cls.FEED_EXPIRE_DAYS * 86400)
            pipe.delete(cls._empty_key(user_id))
            pipe.execute()

            logger.info(f"用户{user_id}时间线缓存已回填，共{len(posts)}条帖子")
            return True
        except Exception as e:
            logger.error(f"回填用户{user_id}时间线缓存失败: {e}")
            return False
    @classmethod
    def get_feed_count(cls,user_id:int):
        '''
        获取用户时间线中的帖子总数（用于分页计算等）
        '''
        try:
            # 封装里没有 zcard，直接访问原生 client
            return redis_cache.zcard(cls._feed_key(user_id)) or 0
        except Exception as e:
            logger.error(f"获取用户{user_id}时间线总数失败: {e}")
            return 0


class ExploreCache:
    '''
    广场Feed缓存
    数据结构:全局单个Sorted Set
    -key:feed:explore
    -score:score_for(sec,post_id)(与关注流同一套微偏移，同秒不重复)
    -member:帖子ID
    '''
    KEY='feed:explore'
    MAX_SIZE=2000       #广场只保留最近2000条，超出裁剪（比个人流大：服务所有人）
    EXPIRE_DAYS=7

    @classmethod
    def add_post(cls,post_id:int,created_at)->bool:
        '''发帖时写入广场(同步，失败仅记日志不影响发帖主流程)'''
        if isinstance(created_at,datetime):
            created_at=_to_timestamp(created_at)
        try:
            pipe=redis_cache.pipeline(transaction=False,for_write=True)
            pipe.zadd(cls.KEY,{str(post_id):_score(int(created_at),int(post_id))})
            pipe.zremrangebyrank(cls.KEY,0,-(cls.MAX_SIZE+1))
            pipe.expire(cls.KEY,cls.EXPIRE_DAYS*86400)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'写入广场缓存失败post_id={post_id}:{e}')
            return False
    @classmethod
    def remove_post(cls,post_id:int)->bool:
        '''删贴时从广场移除'''
        try:
            return bool(redis_cache.zrem(cls.KEY,str(post_id)))
        except Exception as e:
            logger.error(f'从广场移除帖子{post_id}失败:{e}')
            return False
    @classmethod
    def pull_by_cursor(cls,cursor,limit:int=20):
        '''游标拉取广场(与FeedCache.pull_feed_by_cursor同逻辑，无空缓存--全站key长期存在)'''
        try:
            if not redis_cache.exists(cls.KEY):
                return None
            max_score='+inf' if cursor is None else f'({float(cursor[0])}'
            rows=redis_cache.zrevrangebyscore(
                    cls.KEY,max_score,'-inf',start=0,num=limit+1,withscores=True
                    )
            has_more=len(rows)>limit
            rows=rows[:limit]
            if not rows:
                return [],None,False
            post_ids=[
                    (m.decode() if isinstance(m,bytes) else str(m)) for m,_ in rows
                    ]
            next_cursor=(
                encode_cursor(rows[-1][1],rows[-1][0]) if has_more else None
            )
            return post_ids,next_cursor,has_more
        except Exception as e:
            logger.error(f'游标拉取广场失败:{e}')
            return None

    @classmethod
    def batch_fill(cls,posts:list):
        '''DB兜底查询后回填(复用batch_fill_cache的写法)'''
        if not posts:
            return True
        try:
            mapping={}
            for post in posts:
                pid=str(post['id'])
                ts=_to_timestamp(post['created_at'])
                mapping[pid]=_score(int(ts),int(pid))

            pipe=redis_cache.pipeline(transaction=False,for_write=True)
            pipe.zadd(cls.KEY,mapping)
            pipe.zremrangebyrank(cls.KEY,0,-(cls.MAX_SIZE+1))
            pipe.expire(cls.KEY,cls.EXPIRE_DAYS*86400)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'回填广场缓存失败:{e}')
            return False







