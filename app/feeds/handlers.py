import logging
from datetime import datetime
from app.common.events import event_bus
from app.feeds.services import FeedService

logger=logging.getLogger(__name__)
_registered=False


def on_post_created(payload:dict):
    '''发帖后自动推Feed(推/拉 由FeedService内部按粉丝数决定)'''
    try:
        FeedService.publish_post(
                post_id=payload['id'],
                author_id=payload['user_id'],
                created_at=datetime.fromisoformat(payload['created_at']).timestamp(),
                )
    except Exception as e:
        logger.error(f'Feed 推送失败 post_id={payload.get("id")}:{e}')

def on_post_deleted(payload:dict):
    '''删贴后清理Feed时间线(作者+粉丝)'''
    try:
        FeedService.delete_post(
                post_id=payload['post_id'],
                author_id=payload['user_id'],
                )
    except Exception as e:
        logger.error(f'Feed清理失败 post_id={payload.get("post_id")}:{e}')
def register_feed_handlers():
    global _registered
    if _registered:
        return 
    event_bus.subscribe('post.created',on_post_created)
    event_bus.subscribe('post.deleted',on_post_deleted)
    logger.info('Feed模块时间监听器已注册')



