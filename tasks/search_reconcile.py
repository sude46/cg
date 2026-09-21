import logging

from celery import shared_task

from app.posts.repositories import post_repository
from core.metrics import RECONCILE_DIFF_COUNT
from core.redis_cache import redis_cache
from services.search import PostSearchService

logger = logging.getLogger(__name__)

DIRTY_KEY = PostSearchService.DIRTY_KEY


@shared_task
def reconcile_search_index(batch_size: int = 500):
    """ES 索引对账：回灌 search:dirty 中同步失败的帖子。

    以 DB 为准：帖子仍在（未删）→ 重建索引；已删 → 标记删除。
    成功即从 dirty 集合移除，失败保留待下次重试。
    """
    try:
        dirty = redis_cache.smembers(DIRTY_KEY, for_write=True) or set()
        post_ids = []
        for member in dirty:
            try:
                post_ids.append(int(member))
            except (TypeError, ValueError):
                logger.warning(f'[SearchReconcile] 非法脏标记，已清理: {member!r}')
                redis_cache.srem(DIRTY_KEY, member)
        post_ids = post_ids[:batch_size]

        fixed = failed = 0
        for post_id in post_ids:
            try:
                post = post_repository.get_by_id(post_id, force_master=True)
                if post is None or post.deleted_at is not None:
                    ok = PostSearchService.delete_post(post_id)
                else:
                    ok = PostSearchService.index_post(PostSearchService.post_to_doc(post))
                if ok:
                    redis_cache.srem(DIRTY_KEY, post_id)
                    fixed += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.warning(f'[SearchReconcile] 帖子{post_id}回灌失败: {e}')

        RECONCILE_DIFF_COUNT.labels(resource_type='search').set(failed)
        logger.info(
            f'[SearchReconcile] 完成 待处理={len(post_ids)} 修复={fixed} 失败={failed}'
        )
        return {'status': 'success', 'pending': len(post_ids), 'fixed': fixed, 'failed': failed}
    except Exception as e:
        logger.error(f'[SearchReconcile] 对账任务失败: {e}')
        return {'status': 'error', 'message': str(e)}
