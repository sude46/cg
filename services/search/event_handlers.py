'''
搜索模块事件监听器
职责：监听业务实践，同步更新ES索引
'''
import logging

from app.common.events import event_bus
from services.search import PostSearchService, es_client

logger=logging.getLogger(__name__)

def on_post_created(data:dict):
    '''帖子创建事件：索引到ES；失败标记脏索引等待对账'''
    post_id=data.get('id')
    try:
        if es_client.is_available() and PostSearchService.index_post(data):
            logger.debug(f"ES索引创建成功:post_id={post_id}")
            return
        PostSearchService.mark_dirty(post_id)
    except Exception as e:
        logger.warning(f'ES索引创建失败(不影响主流程):{e}')
        PostSearchService.mark_dirty(post_id)
def on_post_updated(data: dict):
    """帖子更新事件：更新 ES；失败标记脏索引等待对账"""
    post_id = data.get('post_id')
    if not post_id:
        return
    try:
        # 只更新提供的字段
        update_fields = {k: v for k, v in data.items() if k != 'post_id'}
        if es_client.is_available() and PostSearchService.update_post(post_id, **update_fields):
            logger.debug(f'ES 索引更新成功: post_id={post_id}')
            return
        PostSearchService.mark_dirty(post_id)
    except Exception as e:
        logger.warning(f'ES 索引更新失败（不影响主流程）: {e}')
        PostSearchService.mark_dirty(post_id)


def on_post_deleted(data: dict):
    """帖子删除事件：从 ES 移除；失败标记脏索引等待对账"""
    post_id = data.get('post_id')
    if not post_id:
        return
    try:
        if PostSearchService.delete_post(post_id):
            logger.debug(f'ES 索引删除成功: post_id={post_id}')
            return
        PostSearchService.mark_dirty(post_id)
    except Exception as e:
        logger.warning(f'ES 索引删除失败（不影响主流程）: {e}')
        PostSearchService.mark_dirty(post_id)


def on_post_like_count_changed(data: dict):
    """帖子点赞数变更事件：更新 ES；失败标记脏索引等待对账"""
    post_id = data.get('post_id')
    like_count = data.get('like_count')
    if not post_id:
        return
    try:
        if es_client.is_available() and PostSearchService.update_post(post_id, like_count=like_count):
            logger.debug(f'ES 点赞数更新成功: post_id={post_id}, like_count={like_count}')
            return
        PostSearchService.mark_dirty(post_id)
    except Exception as e:
        logger.warning(f'ES 点赞数更新失败（不影响主流程）: {e}')
        PostSearchService.mark_dirty(post_id)


def on_post_comment_count_changed(data: dict):
    """帖子评论数变更事件：更新 ES；失败标记脏索引等待对账"""
    post_id = data.get('post_id')
    comment_count = data.get('comment_count')
    if not post_id:
        return
    try:
        if es_client.is_available() and PostSearchService.update_post(
            post_id, comment_count=comment_count
        ):
            logger.debug(
                f'ES 评论数更新成功: post_id={post_id}, comment_count={comment_count}'
            )
            return
        PostSearchService.mark_dirty(post_id)
    except Exception as e:
        logger.warning(f'ES 评论数更新失败（不影响主流程）: {e}')
        PostSearchService.mark_dirty(post_id)


def register_search_event_handlers():
    """注册所有搜索相关的事件监听器"""
    event_bus.subscribe('post.created', on_post_created)
    event_bus.subscribe('post.updated', on_post_updated)
    event_bus.subscribe('post.deleted', on_post_deleted)
    event_bus.subscribe('post.like_count_changed', on_post_like_count_changed)
    event_bus.subscribe('post.comment_count_changed', on_post_comment_count_changed)
    logger.info('搜索模块事件监听器已注册')
