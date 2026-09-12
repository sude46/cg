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

    已知边界：只按 updated_at 补“新增/修改/删除”；若删除操作未更新 updated_at，
    则该删除无法补回（需要持久化待办队列才能严格保证）。
    """
    try:
        since = utcnow() - timedelta(minutes=max(1, int(minutes)))
        posts = post_repository.get_posts_updated_since(since)
        indexed = deleted = failed = 0
        for post in posts:
            try:
                if post.deleted_at is not None:
                    PostSearchService.delete_post(post.id)
                    deleted += 1
                else:
                    PostSearchService.index_post({
                        'id': post.id,
                        'content': post.content,
                        'user_id': post.user_id,
                        'user_name': post.author.username if post.author else None,
                        'image_url': post.image_url,
                        'like_count': post.like_count,
                        'comment_count': post.comment_count,
                        'created_at': post.created_at.isoformat() if post.created_at else None,
                        'is_published': post.is_published,
                        'deleted_at': None,
                    })
                    indexed += 1
            except Exception as e:
                failed += 1
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
