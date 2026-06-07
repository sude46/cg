from celery import shared_task
from app.posts.cache import PostCache
from app.comments.cache import CommentCache
from app.posts.repositories import post_repository
from app.comments.repositories import comment_repository
from core.redis_cache import redis_cache
import logging
import random

logger = logging.getLogger(__name__)

@shared_task
def reconcile_hot_comments(sample_size: int = 50):
    """
    定时对账：扫描热帖，从 DB 重建热评 ZSet
    每轮取 hot:posts:daily 中的帖子，重建其热评排名
    """
    try:
        hot_post_ids, _ = PostCache.get_hot_posts(page=1, per_page=sample_size)
        if not hot_post_ids:
            return {'status': 'success', 'rebuilt': 0}

        fixed = 0
        for post_id in hot_post_ids:
            try:
                # 从 DB 查该帖点赞数最高的 N 条评论
                comments = comment_repository.list_top_by_likes(
                    post_id=post_id,
                    limit=CommentCache.HOT_COMMENTS_PRE_POST
                )
                if comments:
                    comments_data = [
                        {'comment_id': c.id, 'like_count': c.like_count}
                        for c in comments if hasattr(c, 'like_count')
                    ]
                    CommentCache.rebuild_hot_comments(post_id, comments_data)
                else:
                    CommentCache.rebuild_hot_comments(post_id, [])
                fixed += 1
            except Exception as e:
                logger.error(f'[ReconcileHotComments] 重建热评失败 post_id={post_id}: {e}')
                continue

        logger.info(f'[ReconcileHotComments] 对账完成: 重建 {fixed} 个帖子的热评')
        return {'status': 'success', 'rebuilt': fixed}
    except Exception as e:
        logger.error(f'[ReconcileHotComments] 对账任务异常: {e}')
        return {'status': 'failed', 'error': str(e)}
