from celery import shared_task
from app.posts.cache import PostCache
from app.posts.repositories import post_repository
from core .redis_cache import redis_cache
import logging 
import random
from core.metrics import RECONCILE_DIFF_COUNT  # 新增

logger=logging.getLogger(__name__)

@shared_task
def reconcile_post_cache(sample_size:int=500):
    """
    定时对账：每小时抽样比对 Redis 缓存 vs DB
    不一致则删缓存，下次请求自动回填
    """
    try:
        pattern='post:detail:*'
        keys=[]
        for key in redis_cache.scan_iter(match=pattern,count=100):
            key_str=key.decode() if isinstance(key,bytes) else key
            keys.append(key_str)
        if not keys:
            return {'status':'success','checked':0,'fixed':0}
        if len(keys)>sample_size:
            keys=random.sample(keys,sample_size)
        fixed=0
        total_diff = 0  # 用于监控
        checked=0

        for key in keys:
            try:
                parts=key.split(':')
                if len(parts)<3:
                    continue
                post_id=int(parts[-1])

                redis_data=PostCache.get(post_id)
                if not redis_data:
                    continue

                #对账
                db_post=post_repository.get_by_id(post_id, force_master=True)
                if not db_post:
                    PostCache.invalidate(post_id)
                    fixed += 1
                    continue
                checked += 1
                mismatched = False

                # 比对 content
                if redis_data.get('content') != db_post.content:
                    mismatched = True
                    logger.warning(
                        f'[Reconcile] content 不一致 post_id={post_id}'
                    )

                #比对 updated_at
                redis_updated = redis_data.get('updated_at')
                db_updated = db_post.updated_at.isoformat() if db_post.updated_at else None
                if redis_updated and db_updated and redis_updated != db_updated:
                    mismatched = True
                    logger.warning(
                        f'[Reconcile] updated_at 不一致 post_id={post_id}'
                    )
                # 比对 deleted_at
                redis_deleted = redis_data.get('deleted_at')
                db_deleted = db_post.deleted_at.isoformat() if db_post.deleted_at else None
                if redis_deleted != db_deleted:
                    mismatched = True
                if mismatched:
                    total_diff += 1
                    PostCache.invalidate(post_id)
                    fixed += 1
            except Exception as e:
                RECONCILE_DIFF_COUNT.labels(resource_type='post').set(total_diff)
                logger.error(f'[Reconcile] 对账单条异常 key={key}: {e}')
                continue
            RECONCILE_DIFF_COUNT.labels(resource_type='post').set(total_diff)
            logger.info(f'[Reconcile] 对账完成: 检查{checked}条, 修正{fixed}条')
            return {'status': 'success', 'checked': checked, 'fixed': fixed}
    except Exception as e:
        RECONCILE_DIFF_COUNT.labels(resource_type='post').set(total_diff)
        logger.error(f'[Reconcile] 对账任务异常: {e}')
        return {'status': 'failed', 'error': str(e)}
    

                
                


