import logging

from celery import shared_task

from app.comments.repositories import comment_repository
from app.likes.cache import LikeCache
from app.likes.repositories import like_repository
from app.posts.repositories import post_repository
from core import db
from core.redis_cache import redis_cache
from tasks.base_task import MonitoredTask

logger=logging.getLogger(__name__)
DIRTY_LIKES_KEY = "dirty:likes"


def _get_active_like(user_id: int, target_type: str, target_id: int):
    """主库读当前有效点赞行，避免主从延迟让任务误判成 no-op。"""
    if target_type == 'post':
        return like_repository.get_post_like(user_id, target_id, force_master=True)
    return like_repository.get_comment_like(user_id, target_id, force_master=True)


def _create_like(user_id: int, target_type: str, target_id: int):
    if target_type == 'post':
        like_repository.create_post_like(user_id, target_id)
        post_repository.increment_like_count(target_id)
    else:
        like_repository.create_comment_like(user_id, target_id)
        comment_repository.increment_like_count(target_id)


def _delete_like(like, target_type: str, target_id: int):
    like_repository.delete_like(like)
    if target_type == 'post':
        post_repository.decrement_like_count(target_id)
    else:
        comment_repository.decrement_like_count(target_id)


def _redis_says_liked(user_id: int, target_type: str, target_id: int):
    """从 Redis 主节点读用户当前是否点赞；None 表示 Redis 不可用。"""
    try:
        key = LikeCache._user_liked_key(user_id, target_type)
        return bool(redis_cache.sismember(key, str(target_id), for_write=True))
    except Exception as e:
        logger.warning(
            f'[celery] 读取 Redis 点赞状态失败 uid={user_id} {target_type}:{target_id}: {e}'
        )
        return None


def _apply_action_fallback(user_id: int, target_type: str, target_id: int, action: str):
    """Redis 不可读取时退回旧语义：按任务携带的 action 执行一次。"""
    like = _get_active_like(user_id, target_type, target_id)
    if action == 'create' and like is None:
        _create_like(user_id, target_type, target_id)
    elif action == 'delete' and like is not None:
        _delete_like(like, target_type, target_id)
    db.session.commit()


def _sync_like_state(user_id: int, target_type: str, target_id: int, action: str):
    """把 DB 收敛到 Redis 的当前状态，而不是盲目重放旧 action。

    返回 True/False 表示 Redis 期望状态；None 表示 Redis 不可用、走了 fallback。
    """
    desired = _redis_says_liked(user_id, target_type, target_id)
    if desired is None:
        _apply_action_fallback(user_id, target_type, target_id, action)
        return None

    like = _get_active_like(user_id, target_type, target_id)
    changed = False
    if desired and like is None:
        _create_like(user_id, target_type, target_id)
        changed = True
    elif not desired and like is not None:
        _delete_like(like, target_type, target_id)
        changed = True

    if changed:
        db.session.commit()
    return desired


@shared_task(base=MonitoredTask,bind=True, max_retries=3,default_retry_delay=5)
def async_like_to_do(self,user_id:int,target_type:str,target_id:int,action:str,pending_id:str):
    """
    将 Redis 当前点赞状态同步到 DB。

    action 只是任务产生时的意图提示，不作为最终依据：
    - Redis 现在是已点赞 -> DB 必须有有效行；
    - Redis 现在是未点赞 -> DB 不能有有效行。

    这样 create/delete 任务乱序、重复投递时最终都会收敛到 Redis 当前状态。
    """
    dirty_tag = f"{target_type}:{target_id}"
    try:
        desired = _sync_like_state(user_id, target_type, target_id, action)

        # 只有 DB 与 Redis 当前状态一致时才允许清 dirty
        if desired is not None:
            like = _get_active_like(user_id, target_type, target_id)
            if bool(like) != desired:
                raise RuntimeError(
                    f'点赞状态未收敛 {target_type}:{target_id} desired={desired}'
                )

        LikeCache.delete_dirty(target_type,target_id)
        redis_cache.srem(DIRTY_LIKES_KEY,dirty_tag)
        logger.info(f'[celery] 清理脏标记成功 {dirty_tag}')

        return{'status':'success','pending_id':pending_id}
    except Exception as e:
        db.session.rollback()
        logger.error(f'[celery] 同步点赞到DB失败 pending_id: {pending_id}, error: {e}')
        raise self.retry(exc=e)
