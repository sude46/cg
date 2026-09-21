import logging
from datetime import timedelta

from celery import shared_task

from app.common.database import utcnow
from app.posts.repositories import post_repository
from services.search import PostSearchService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def reindex_recent_posts(self, minutes: int = 60):
    """ES 降级恢复后，补索引最近 N 分钟被创建/修改/软删的帖子。

    软删会触发 Post.updated_at 的 onupdate，故删除也能被该窗口覆盖；
    窗口外的遗漏由 reconcile_search_index 依 search:dirty 兜底。
    """
    try:
        since = utcnow() - timedelta(minutes=max(1, int(minutes)))
        posts = post_repository.get_posts_updated_since(since)
        indexed = deleted = failed = 0
        for post in posts:
            try:
                if post.deleted_at is not None:
                    if PostSearchService.delete_post(post.id):
                        deleted += 1
                    else:
                        failed += 1
                        PostSearchService.mark_dirty(post.id)
                elif PostSearchService.index_post(PostSearchService.post_to_doc(post)):
                    indexed += 1
                else:
                    failed += 1
                    PostSearchService.mark_dirty(post.id)
            except Exception as e:
                failed += 1
                PostSearchService.mark_dirty(post.id)
                logger.warning(f'[SearchReindex] 帖子{post.id}补索引失败: {e}')
        logger.info(
            f'[SearchReindex] 补索引完成 indexed={indexed} deleted={deleted} '
            f'failed={failed} window={minutes}min'
        )
        return {
            'status': 'success', 'indexed': indexed,
            'deleted': deleted, 'failed': failed
        }
    except Exception as e:
        logger.error(f'[SearchReindex] 补索引任务失败: {e}')
        raise self.retry(exc=e)
