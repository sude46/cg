import hashlib
import logging
import time
from datetime import UTC
from typing import Any

from core.redis_cache import redis_cache
from services.search.document import PostDocument, SearchBackendError
from services.search.repositories import PostSearchRepository

logger=logging.getLogger(__name__)
class PostSearchService:
    '''
    帖子搜索fuwu
    这个类不直接操作ES，而是调用PostSearchRepository
    '''
    HOT_SEARCH_KEY='hot:searches'
    HOT_SEARCH_TTL=7*86400
    HOT_SEARCH_MAX=1000
    # 索引同步失败/疑似不一致的帖子ID集合，由 reconcile_search_index 定时回灌
    DIRTY_KEY='search:dirty'

    # ==================== 搜索降级（熔断） ====================
    DEGRADE_KEY='search:es:degraded'          # 熔断标记（窗口内不再探测 ES）
    RECOVER_KEY='search:es:recover_pending'   # 降级起点（用于恢复后估算补索引窗口）
    RECOVER_KEY_TTL=86400
    DEFAULT_DEGRADE_TTL=30
    DEFAULT_FALLBACK_MIN_LEN=2
    DEFAULT_FALLBACK_MAX_PER_PAGE=20
    DEFAULT_FALLBACK_CACHE_TTL=10
    @classmethod
    def index_post(cls,post_data:dict[str,Any]):
        '''
        搜索帖子（双写同步调用)
        Args:
            post_data: 帖子数据字典，包含：
                - id: 帖子ID
                - content: 内容
                - user_id: 用户ID
                - username: 用户名
                - created_at: 创建时间
                - ...其他字段
        '''
        #计算机热度分数
        post_data['hot_score']=cls._calculate_hot_score(post_data)
        #兜底默认值：查询侧强制过滤 is_deleted=False / is_published=True
        post_data['is_deleted']=post_data.get('is_deleted',False)
        post_data['is_published']=post_data.get('is_published',True)
        return PostDocument.index(post_data['id'], post_data)
    @classmethod
    def update_post(cls,post_id:int,**fields):
        '''更新帖子'''
        return PostDocument.update(post_id,fields)

    @classmethod
    def delete_post(cls,post_id:int):
        '''删除帖子'''
        return PostDocument.delete(post_id)

    @classmethod
    def mark_dirty(cls,post_id:int):
        '''标记索引需重建（事件同步失败时调用，交由对账任务回灌）'''
        if not post_id:
            return
        try:
            redis_cache.sadd(cls.DIRTY_KEY,post_id)
        except Exception as e:
            logger.warning(f'[Search] 标记脏索引失败 post_id={post_id}: {e}')

    @staticmethod
    def post_to_doc(post)->dict[str,Any]:
        '''ORM Post → ES 文档（索引/补索引/对账共用，避免字段漂移）'''
        return {
            'id':post.id,
            'content':post.content,
            'user_id':post.user_id,
            'user_name':post.author.username if post.author else None,
            'image_url':post.image_url,
            'like_count':post.like_count,
            'comment_count':post.comment_count,
            'created_at':post.created_at.isoformat() if post.created_at else None,
            'is_published':post.is_published,
            'deleted_at':None,
        }
    @staticmethod
    def search(query:str,page:int=1,per_page:int=20,user_id:int | None=None,sort_by:str='relevance'):
        '''搜索帖子（主接口）。

        ES 正常：返回 ES 结果（0 结果就是 0 结果，不回退 DB）。
        ES 故障：进入熔断窗口，窗口内走带护栏的 DB 降级；窗口结束自动探测恢复。
        '''
        # 热搜词统计（失败不影响搜索）
        if query and query.strip():
            PostSearchService._record_search_keyword(query.strip())

        # 熔断中：不再探测 ES，直接降级
        if PostSearchService._is_degraded():
            return PostSearchService._degraded_search(query,page,per_page)

        try:
            posts,total=PostSearchRepository.search(
                query=query,
                page=page,
                per_page=per_page,
                user_id=user_id,
                sort_by=sort_by
            )
        except SearchBackendError as e:
            logger.error(f'[Search] ES 查询失败，进入降级: {e}')
            PostSearchService._enter_degrade()
            return PostSearchService._degraded_search(query,page,per_page)

        # ES 正常：若此前发生过降级，清理标记并补写窗口内的索引
        PostSearchService._try_recover()

        return {
            'items':posts,
            'total':total,
            'pagination':PostSearchService._pagination(page,per_page,total)
        }

    # ==================== 熔断控制 ====================

    @staticmethod
    def _config(name,default):
        """读取配置：有 app context 时优先取 app.config，否则用默认值"""
        try:
            from flask import current_app, has_app_context
            if has_app_context():
                value=current_app.config.get(name)
                if value is not None:
                    return value
        except Exception:
            pass
        return default

    @staticmethod
    def _is_degraded():
        try:
            return redis_cache.exists(PostSearchService.DEGRADE_KEY,for_write=True)>0
        except Exception:
            return False

    @classmethod
    def _enter_degrade(cls):
        """设置熔断标记（用 setnx 保证 TTL 不被随机抖动放大）"""
        ttl=int(cls._config('SEARCH_DEGRADE_TTL',cls.DEFAULT_DEGRADE_TTL))
        try:
            redis_cache.setnx(cls.DEGRADE_KEY,'1',expire=ttl)
            # 仅首次降级记录起点，恢复后据此估算补索引窗口
            redis_cache.setnx(cls.RECOVER_KEY,str(int(time.time())),expire=cls.RECOVER_KEY_TTL)
        except Exception as e:
            logger.warning(f'设置搜索降级标记失败: {e}')

    @classmethod
    def _try_recover(cls):
        """ES 恢复：清理熔断标记并调度补索引"""
        try:
            started=redis_cache.get(cls.RECOVER_KEY,for_write=True)
            if started is None:
                redis_cache.delete(cls.DEGRADE_KEY)
                return
            try:
                minutes=int((time.time()-int(started))/60)+1
            except Exception:
                minutes=60
            minutes=min(max(minutes,1),1440)
            redis_cache.delete(cls.RECOVER_KEY)
            redis_cache.delete(cls.DEGRADE_KEY)
            cls._schedule_recovery_reindex(minutes)
        except Exception as e:
            logger.warning(f'搜索恢复处理失败: {e}')

    @staticmethod
    def _schedule_recovery_reindex(minutes:int):
        """补索引为尽力而为，失败不影响搜索"""
        try:
            from tasks.search_tasks import reindex_recent_posts
            reindex_recent_posts.delay(minutes=minutes)
            logger.info(f'[Search] ES 恢复，已调度补索引窗口 {minutes} 分钟')
        except Exception as e:
            logger.warning(f'[Search] 调度补索引失败（可手动执行 reindex_recent_posts）: {e}')

    # ==================== 降级查询（带护栏） ====================

    @classmethod
    def _degraded_search(cls,query:str,page:int=1,per_page:int=20):
        mode=cls._config('SEARCH_DEGRADE_MODE','fallback')
        if mode=='unavailable':
            from app.common.exceptions import ServiceUnavailableError
            raise ServiceUnavailableError('搜索服务暂时不可用，请稍后重试')

        keyword=(query or '').strip()
        min_len=int(cls._config('SEARCH_FALLBACK_MIN_LEN',cls.DEFAULT_FALLBACK_MIN_LEN))
        if not cls._meets_min_length(keyword,min_len):
            return cls._empty_result(page,per_page)

        max_pp=int(cls._config('SEARCH_FALLBACK_MAX_PER_PAGE',cls.DEFAULT_FALLBACK_MAX_PER_PAGE))
        per_page=min(max(1,per_page),max_pp)
        ttl=int(cls._config('SEARCH_FALLBACK_CACHE_TTL',cls.DEFAULT_FALLBACK_CACHE_TTL))

        from app.posts.repositories import post_repository
        cache_key=cls._fallback_cache_key(keyword,page,per_page)
        ids=total=None
        try:
            cached=redis_cache.get(cache_key,for_write=False)
            if isinstance(cached,dict) and isinstance(cached.get('ids'),list):
                ids=cached['ids']
                total=int(cached.get('total',len(ids)))
        except Exception:
            pass
        if ids is None:
            ids,total=post_repository.search_post_ids(keyword,page,per_page)
            try:
                redis_cache.set(cache_key,{'ids':ids,'total':total},expire=ttl,for_write=True)
            except Exception:
                pass
        posts=post_repository.get_by_ids(ids)
        return {
            'items':posts,
            'total':total,
            'fallback':True,
            'pagination':cls._pagination(page,per_page,total)
        }

    @staticmethod
    def _meets_min_length(keyword:str,min_len:int)->bool:
        if not keyword:
            return False
        if len(keyword)>=min_len:
            return True
        # 单个 CJK 字符放行（中文单字常见是有效搜索词）
        return len(keyword)==1 and '\u4e00'<=keyword[0]<='\u9fff'

    @staticmethod
    def _fallback_cache_key(keyword:str,page:int,per_page:int)->str:
        raw=f'{keyword}|{page}|{per_page}'.encode()
        return 'search:fallback:ids:'+hashlib.md5(raw).hexdigest()

    @staticmethod
    def _pagination(page:int,per_page:int,total:int)->dict:
        pages=(total+per_page-1)//per_page if total>0 else 0
        return {
            'page':page,
            'per_page':per_page,
            'total':total,
            'pages':pages,
            'has_next':page<pages,
            'has_prev':page>1
        }

    @staticmethod
    def _empty_result(page:int,per_page:int)->dict:
        return {
            'items':[],
            'total':0,
            'fallback':True,
            'pagination':PostSearchService._pagination(page,per_page,0)
        }

    @classmethod
    def _record_search_keyword(cls,keyword:str):
        '''热搜词统计（Redis ZSet），失败不影响搜索'''
        try:
            redis_cache.zincrby(cls.HOT_SEARCH_KEY,keyword,1)
            redis_cache.expire(cls.HOT_SEARCH_KEY,cls.HOT_SEARCH_TTL)
            redis_cache.zremrangebyrank(cls.HOT_SEARCH_KEY,0,-(cls.HOT_SEARCH_MAX+1))
        except Exception as e:
            logger.warning(f'记录热搜词失败:{e}')

    @classmethod
    def get_hot_searches(cls,size:int=10):
        '''热搜榜（Redis ZSet 按分数倒序）'''
        size=min(50,max(1,size))
        try:
            results=redis_cache.zrevrange(cls.HOT_SEARCH_KEY,0,size-1,withscores=True)
            hot_searches=[]
            for item in results or []:
                if isinstance(item,(list,tuple)):
                    keyword,score=item[0],item[1]
                else:
                    continue
                if isinstance(keyword,bytes):
                    keyword=keyword.decode()
                hot_searches.append({'keyword':keyword,'count':int(score)})
            return hot_searches
        except Exception as e:
            logger.error(f'获取热搜榜失败:{e}')
            return []

    @classmethod
    def get_search_suggestions(cls,keyword:str,size:int=10):
        '''搜索建议（自动补全）：走 ES suggest 字段（IK+edge_ngram），ES 不可用时优雅返回空'''
        keyword=(keyword or '').strip()
        if not keyword:
            return []
        size=min(50,max(1,size))
        return PostDocument.suggest(keyword,size)
    @classmethod
    def reindex_all(cls,fetch_func,batch_size:int=100):
        '''
        全量重建索引
        Args:
            fetch_func: 获取数据的函数，接收(offset, limit)返回帖子列表
            batch_size: 批次大小

        Returns:
            (成功数, 失败数)

        '''
        #删除旧索引
        PostDocument.delete_index()
        PostDocument.create_index()
        success=failed=0
        offset=0
        while True:
            #调用外部传入的获取函数
            posts=fetch_func(offset,batch_size)
            if not posts:
                break
            for post in posts:
                try:
                    if cls.index_post(post):
                        success+=1
                    else:
                        failed+=1
                except Exception as e:
                    logger.error(f"索引帖子失败:{e}")
                    failed+=1
            offset+=batch_size
            logger.info(f"已处理 {offset} 条帖子，成功 {success} 条，失败 {failed} 条")
        logger.info(f"重建索引完成，总成功 {success} 条，总失败 {failed} 条")
        return success,failed

    @classmethod
    def reindex_all_posts(cls,batch_size:int=100):
        '''从数据库全量重建帖子索引（manage_es.py reindex 使用）'''
        from app.posts.repositories import post_repository

        def fetch(offset,limit):
            posts=post_repository.list_posts_for_reindex(offset,limit)
            return [cls.post_to_doc(p) for p in posts]

        return cls.reindex_all(fetch,batch_size)

    @staticmethod
    def _calculate_hot_score(post_data:dict[str,Any])->float:
        '''
        计算帖子热度分数
        算法：点赞 + 评论*2 + 时间衰减
        '''
        from datetime import datetime

        like_count=post_data.get('like_count',0)
        comment_count=post_data.get('comment_count',0)
        score=like_count+comment_count*2
        time_bonus=0.0
        created_at=post_data.get('created_at')
        if created_at:
            if isinstance(created_at,str):
                created_at=datetime.fromisoformat(created_at.replace('Z','+00:00'))
            if created_at.tzinfo is None:
                created_at=created_at.replace(tzinfo=UTC)
            hours_since=(datetime.now(UTC)-created_at).total_seconds()/3600
            #24小时内的新帖有加成
            time_bonus=max(0,24-hours_since)*10

        return score+time_bonus


