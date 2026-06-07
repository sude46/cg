from celery import shared_task
from core import db
from app.likes.repositories import like_repository
from app.posts.repositories import post_repository
from app.likes.cache import LikeCache
from core.redis_cache import redis_cache
from app.comments.repositories import comment_repository
import logging


logger=logging.getLogger(__name__)
DIRTY_LIKES_KEY = "dirty:likes"


@shared_task(bind=True, max_retries=3,default_retry_delay=5)
def async_like_to_do(self,user_id:int,target_type:str,target_id:int,action:str,pending_id:str):
    """
    异步将Redis点赞状态同步到DB
    action:'create'or'delete'
    pending_id:幂等去重键（可用Redis Set或唯一索引防重）

    """
    dirty_tag = f"{target_type}:{target_id}"
    try:
        if action=='create':
            if target_type=='post':
                existing=like_repository.get_post_like(user_id,target_id)
                if not existing:
                    like_repository.create_post_like(user_id,target_id)
                    post_repository.increment_like_count(target_id)
                    db.session.commit()
                    logger.info(f'[celery] 同步点赞到DB成功 pending_id: {pending_id}')
            else:
                existing=like_repository.get_comment_like(user_id,target_id)
                if not existing:
                    like_repository.create_comment_like(user_id,target_id)
                    comment_repository.increment_like_count(target_id)
                    db.session.commit()
                    logger.info(f'[celery] 同步点赞到DB成功 pending_id: {pending_id}')
        elif action=='delete':
            if target_type=='post':
                like=like_repository.get_post_like(user_id,target_id)
            else:
                like=like_repository.get_comment_like(user_id,target_id)
            if like:
                like_repository.delete_like(like)
                if target_type=='post':
                    post_repository.decrement_like_count(target_id)
                else:
                    comment_repository.decrement_like_count(target_id)
                db.session.commit()
                logger.info(f'[celery] 同步取消点赞到DB成功 pending_id: {pending_id}')
        #=====只有DB提交成功，才清理脏标记======
        LikeCache.delete_dirty(target_type,target_id)
        redis_cache.srem(DIRTY_LIKES_KEY,dirty_tag)
        logger.info(f'[celery] 清理脏标记成功 {dirty_tag}')
        
        
        return{'status':'success','pending_id':pending_id}
    except Exception as e:
        db.session.rollback()
        logger.error(f'[celery] 同步点赞到DB失败 pending_id: {pending_id}, error: {e}')
        raise self.retry(exc=e)