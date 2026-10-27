import logging

from celery import shared_task

from app.comments.repositories import comment_repository
from app.likes.cache import LikeCache
from app.likes.reconcile import (
    NOOP,
    REBUILD_REDIS,
    UPDATE_DB,
    cache_is_complete,
    count_likes_from_master,
    decide_action,
    has_pending,
    read_redis_count_from_master,
)
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

    方向守卫:
    - dirty_key 还在(可能仍有任务在途) -> 本轮跳过,下轮再处理
    - Redis 计数残缺/无法证明完整 -> 用 DB 重建 Redis,绝不反向覆盖 DB
    - Redis 完整且比 DB 多 -> 把增量补回 DB
    - 相等 -> 无需修改

    commit 成功后才清 dirty,避免提交失败后永久失去重试机会。
    '''
    total_diff=0
    clear_targets=[]
    try:
        #从dirty:likes取一批待对账的target
        dirty_members=redis_cache.smembers(DIRTY_LIKES_KEY,for_write=True)
        if not dirty_members:
            logger.info("[Reconcile] dirty:likes为空，无需对账")
            return

        #解析过滤器
        targets=[]
        for m in dirty_members:
            tag=m.decode() if isinstance(m,bytes) else m
            parts=tag.split(':')
            if len(parts)!=2:
                continue
            t_type,t_id=parts[0],int(parts[1])
            if t_type==target_type_filter:
                targets.append((t_type,t_id))
        # 限制批次大小，防止一次任务太长
        targets=targets[:batch_size]
        logger.info(f"[Reconcile] 发现 {len(targets)} 个 {target_type_filter} 需要对账")

        for t_type,t_id in targets:
            if has_pending(t_type,t_id):
                logger.info(f"[Reconcile] {t_type}:{t_id} 仍有在途任务，本轮跳过")
                continue

            # Redis 计数从主节点读，避免 Redis 副本延迟制造假 diff
            redis_count=read_redis_count_from_master(t_type,t_id)
            # DB 计数必须走主库
            db_count=count_likes_from_master(t_type,t_id)
            complete=cache_is_complete(t_type,t_id,redis_count)
            action=decide_action(redis_count,db_count,complete,pending=False)

            if action==REBUILD_REDIS:
                total_diff += 1 if redis_count!=db_count else 0
                # 只重建 Redis count，不写 DB；likers 不完整时保持保守
                LikeCache.set_like_count(t_id,db_count,t_type)
                logger.warning(
                    f'[Reconcile] 差异发现 {t_type}:{t_id} '
                    f'Redis={redis_count} DB={db_count} complete={complete}，'
                    f'以 DB 为准重建 Redis'
                )
                clear_targets.append((t_type,t_id))
            elif action==UPDATE_DB:
                total_diff += 1
                if t_type=='post':
                    post_repository.update_like_count(t_id,redis_count)
                elif t_type=='comment':
                    comment_repository.update_like_count(t_id,redis_count)
                logger.warning(
                    f'[Reconcile] 差异发现 {t_type}:{t_id} '
                    f'Redis={redis_count} DB={db_count}，缓存完整，补 DB'
                )
                clear_targets.append((t_type,t_id))
            elif action==NOOP:
                clear_targets.append((t_type,t_id))

        # 先提交，成功后才清 dirty
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            RECONCILE_DIFF_COUNT.labels(resource_type='like').set(total_diff)
            logger.error(f'[Reconcile] DB 提交失败，保留 dirty 待下轮: {e}')
            return

        for t_type,t_id in clear_targets:
            redis_cache.srem(DIRTY_LIKES_KEY,f"{t_type}:{t_id}")
            LikeCache.delete_dirty(t_type,t_id)

        RECONCILE_DIFF_COUNT.labels(resource_type='like').set(total_diff)
        logger.info(f'[Reconcile] 完成: 修正 {total_diff} 条差异')

    except Exception as e:
        db.session.rollback()
        logger.error(f'[Reconcile] 对账任务异常: {e}')
