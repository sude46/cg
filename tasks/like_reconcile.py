import logging

from celery import shared_task

from app.comments.repositories import comment_repository
from app.likes.cache import LikeCache
from app.likes.repositories import like_repository
from app.posts.repositories import post_repository
from core import db
from core.metrics import RECONCILE_DIFF_COUNT
from core.redis_cache import redis_cache

logger=logging.getLogger(__name__)

DIRTY_LIKES_KEY="dirty:likes"


@shared_task
def reconcile_like_counts(target_type_filter='post', batch_size=500):
    '''
    服务端定时对账:只处理dirty:likes里的帖子(Celery失败/延迟的)
    不在全量扫描Redis,动态调度，防止空跑
    '''
    try:
        total_diff = 0
        #从dirty:likes取一批待对账的target
        dirty_members=redis_cache.smembers(DIRTY_LIKES_KEY)
        if not dirty_members:
            logger.info("[Reconcile] dirty:likes为空，无需对账")
            return

        #解析过滤器
        targets=[]
        for m in dirty_members:
            tag=m.decode() if isinstance(m,bytes) else m
            parts=tag.split(':')
            if len(parts)==2:
                t_type,t_id=parts[0],int(parts[1])
                if t_type==target_type_filter:
                    targets.append((t_type,t_id))
        # 限制批次大小，防止一次任务太长
        targets = targets[:batch_size]
        logger.info(f"[Reconcile] 发现 {len(targets)} 个 {target_type_filter} 需要对账")

        for t_type,t_id in targets:
            #Redis计数（有先读Counter,降级SCARD）
            redis_count=LikeCache.get_like_count(t_id,t_type) or 0
            if redis_count is None:
                continue
            # DB 计数（读操作走从库）
            if t_type == 'post':
                db_count = like_repository.count_likes_for_post(t_id)
            else:
                db_count = like_repository.count_likes_for_comment(t_id)

            # 差异比对：以 Redis 为准修正 DB
            if redis_count != db_count:
                total_diff += 1
                logger.warning(
                    f'[Reconcile] 差异发现 {t_type}:{t_id} '
                    f'Redis={redis_count} DB={db_count}，以 Redis 为准修正 DB'
                )
                if t_type == 'post':
                    post_repository.update_like_count(t_id, redis_count)
                elif t_type == 'comment':
                    comment_repository.update_like_count(t_id, redis_count)

            # 清标记：从 dirty:likes 移除 + 删除 dirty_key
            redis_cache.srem(DIRTY_LIKES_KEY, f"{t_type}:{t_id}")
            LikeCache.delete_dirty(t_type, t_id)

        # 统一提交事务（Repository 不再自行 commit）
        try:
            db.session.commit()
            RECONCILE_DIFF_COUNT.labels(resource_type='like').set(total_diff)
            logger.info(f'[Reconcile] 完成: 修正 {total_diff} 条差异')
        except Exception as e:
            db.session.rollback()
            RECONCILE_DIFF_COUNT.labels(resource_type='like').set(total_diff)
            logger.error(f'[Reconcile] DB 提交失败: {e}')

    except Exception as e:
        logger.error(f'[Reconcile] 对账任务异常: {e}')


