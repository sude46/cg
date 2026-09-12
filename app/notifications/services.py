import logging

from sqlalchemy.exc import IntegrityError

from app.common.events import event_bus
from app.common.exceptions import (
    DatabaseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.notifications.cache import NotificationCache
from app.notifications.repositories import notification_repository
from app.notifications.schemas import notification_schema, notifications_schema
from app.users.repositories import user_repository
from core import db
from core.metrics import NOTIFICATION_OPERATIONS

logger = logging.getLogger(__name__)


def _handle_comment_created(event_data: dict):
    """
    处理评论创建事件，创建通知
    事件数据格式：{
        'user_id': 被通知用户ID（帖子作者）,
        'actor_id': 评论者ID,
        'type': 'comment',
        'comment_id': 评论ID,
        'post_id': 帖子ID,
        'content': 评论内容
    }
    """
    try:
        NotificationService.create_notification({
            'user_id': event_data.get('user_id'),
            'actor_id': event_data.get('actor_id'),
            'type': 'comment',
            'comment_id': event_data.get('comment_id'),
            'content': event_data.get('content')
        })
    except Exception as e:
        # 通知创建失败不应影响评论创建流程
        logger.error(f"Failed to create notification for comment: {e}")


class NotificationService:
    @staticmethod
    def create_notification(data: dict):
        user_id = data.get('user_id')
        actor_id = data.get('actor_id')
        if not user_id:
            raise ValidationError('缺少 recipient user_id')
        if not user_repository.get_by_id(user_id):
            raise ResourceNotFoundError(f"用户(ID:{user_id})不存在")
        if actor_id and not user_repository.get_by_id(actor_id):
            raise ResourceNotFoundError(f"触发用户(ID:{actor_id})不存在")

        # 转换资源字段
        notif_type = data.get('type')
        if notif_type == 'comment':
            resource_id = data.get('comment_id')
            resource_type = 'comment'
        elif notif_type == 'like':
            resource_id = data.get('post_id') or data.get('comment_id')
            resource_type = 'post' if data.get('post_id') else 'comment'
        else:
            resource_id = data.get('post_id') or data.get('comment_id')
            resource_type = 'post' if data.get('post_id') else 'comment'

        notif_data = {
            'user_id': user_id,
            'actor_id': actor_id,
            'type': notif_type,
            'resource_id': resource_id,
            'resource_type': resource_type,
            'content': data.get('content')
        }
        # 移除 None 值
        notif_data = {k: v for k, v in notif_data.items() if v is not None}

        try:
            notif = notification_repository.create_notification(notif_data)
            db.session.commit()

            # 缓存：清除空标记 + 递增未读数 + 强一致标记
            NotificationCache.invalidate_empty(user_id)
            NotificationCache.increment_unread(user_id)
            NotificationCache.mark_recently_modified(user_id)
            NOTIFICATION_OPERATIONS.labels(action='create', result='success').inc()
            return notification_schema.dump(notif)
        except IntegrityError:
            db.session.rollback()
            NOTIFICATION_OPERATIONS.labels(action='create', result='error').inc()
            raise DatabaseError('创建通知失败，数据库约束错误')
        except Exception as e:
            db.session.rollback()
            logger.error('创建通知失败: %s', e)
            if isinstance(e, (ResourceNotFoundError, ValidationError)):
                raise
            NOTIFICATION_OPERATIONS.labels(action='create', result='error').inc()
            raise DatabaseError(f'创建通知失败: {e}')

    @staticmethod
    def get_notification_by_id(notification_id: int, user_id: int):
        notif = notification_repository.get_by_id(notification_id, user_id)
        if not notif:
            raise ResourceNotFoundError(f'通知(ID:{notification_id})不存在或无权访问')
        NOTIFICATION_OPERATIONS.labels(action='get', result='success').inc()
        return notification_schema.dump(notif)

    @staticmethod
    def get_user_notifications(user_id: int, page: int = 1, per_page: int = 20, unread_only: bool = False):
        pagination_result = notification_repository.list_by_user(
            user_id=user_id,
            page=page,
            per_page=per_page,
            unread_only=unread_only
        )
        # 兼容 Pagination 对象和 dict
        if isinstance(pagination_result, dict):
            raw_items = pagination_result.get('items', [])
            pagination_info = pagination_result.get('pagination', {})
        else:
            raw_items = getattr(pagination_result, 'items', [])
            pagination_info = {
                'total': getattr(pagination_result, 'total', 0),
                'pages': getattr(pagination_result, 'pages', 1),
                'page': getattr(pagination_result, 'page', page),
                'per_page': getattr(pagination_result, 'per_page', per_page),
                'has_prev': getattr(pagination_result, 'has_prev', False),
                'has_next': getattr(pagination_result, 'has_next', False)
            }
        items = notifications_schema.dump(raw_items) if raw_items else []
        if not isinstance(items, list):
            items = []

        # 缓存：查未读数（Cache-Aside）
        unread_count = NotificationCache.get_unread_count(user_id)
        if unread_count is None:
            #强一致窗口内（用户刚创建/已读通知），强制走主库，放止主从延迟旧值回跳
            force_master = NotificationCache.is_recently_modified(user_id)
            if unread_only:
                # 分页 total 本身是从库读的，窗口内直接主库 count 更稳
                total_unread = (notification_repository.count_unread(user_id, force_master=True)
                                if force_master
                                else pagination_info.get('total', 0))
            else:
                total_unread = notification_repository.count_unread(user_id, force_master=force_master)
            if total_unread == 0:
                NotificationCache.set_empty(user_id)
            else:
                NotificationCache.set_unread_count(user_id, total_unread)
            unread_count = total_unread
        NOTIFICATION_OPERATIONS.labels(action='list', result='success').inc()
        return {'items': items, 'pagination': pagination_info, 'unread_count': unread_count}

    @staticmethod
    def mark_as_read(notification_id: int, user_id: int):
        try:
            notif = notification_repository.get_by_id(notification_id, user_id)
            if not notif:
                raise ResourceNotFoundError('通知不存在或无权访问')
            notification_repository.mark_as_read(notif)
            db.session.commit()

            # 缓存：递减未读数 + 延迟双删 + 强一致标记
            NotificationCache.decrement_unread(user_id)
            NotificationCache.double_invalidate_unread(user_id)
            NotificationCache.mark_recently_modified(user_id)
            NOTIFICATION_OPERATIONS.labels(action='mark_read', result='success').inc()
            return notification_schema.dump(notif)
        except Exception as e:
            db.session.rollback()
            logger.error('标记通知为已读失败: %s', e)
            if isinstance(e, ResourceNotFoundError):
                raise
            NOTIFICATION_OPERATIONS.labels(action='mark_read', result='error').inc()
            raise DatabaseError(f'标记通知为已读失败: {e}')

    @staticmethod
    def mark_all_as_read(user_id):
        try:
            notification_repository.mark_all_as_read(user_id)
            db.session.commit()

            # 缓存：未读计数归零 + 延迟双删 + 强一致标记
            NotificationCache.clear_unread(user_id)
            NotificationCache.double_invalidate_unread(user_id)
            NotificationCache.mark_recently_modified(user_id)
            NOTIFICATION_OPERATIONS.labels(action='mark_all_read', result='success').inc()
        except Exception as e:
            db.session.rollback()
            logger.error('标记所有通知为已读失败: %s', e)
            NOTIFICATION_OPERATIONS.labels(action='mark_all_read', result='error').inc()
            raise DatabaseError(f'标记所有通知为已读失败: {e}')

    @staticmethod
    def delete_notification(notification_id: int, user_id: int):
        try:
            notif = notification_repository.get_by_id(notification_id, user_id)
            if not notif:
                raise ResourceNotFoundError('通知不存在或无权访问')
            notification_repository.delete(notif)
            db.session.commit()

            # 缓存：清未读 + 延迟双删 + 强一致标记
            NotificationCache.clear_unread(user_id)
            NotificationCache.double_invalidate_unread(user_id)
            NotificationCache.mark_recently_modified(user_id)
            NOTIFICATION_OPERATIONS.labels(action='delete', result='success').inc()
        except Exception as e:
            db.session.rollback()
            logger.error('删除通知失败: %s', e)
            if isinstance(e, ResourceNotFoundError):
                raise
            NOTIFICATION_OPERATIONS.labels(action='delete', result='error').inc()
            raise DatabaseError(f'删除通知失败: {e}')


def register_notification_event_handlers():
    """注册通知模块的事件订阅（由 factory.py 在 app 初始化时调用）"""
    event_bus.subscribe('comment.created', _handle_comment_created)

