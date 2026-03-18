from app.notifications.services import NotificationService as DomainNotificationService
from app.notifications.repositories import notification_repository
from app.notifications.models import Notification
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """兼容 facade：适配旧顶层通知接口到 `app.notifications.services`。"""

    @staticmethod
    def create_notification(recipient_id: int, actor_id: int, notification_type: str, post_id: int = None, comment_id: int = None):
        data = {
            'user_id': recipient_id,
            'actor_id': actor_id,
            'notification_type': notification_type,
            'post_id': post_id,
            'comment_id': comment_id,
        }
        return DomainNotificationService.create_notification(data)

    @staticmethod
    def get_user_notifications(user_id: int, page: int = 1, per_page: int = 20, unread_only: bool = False):
        res = DomainNotificationService.get_user_notifications(user_id, page, per_page, unread_only)
        return {'notifications': res.get('items', []), 'pagination': res.get('pagination', {})}

    @staticmethod
    def mark_as_read(user_id: int, notification_ids: list[int]):
        # 支持批量标记；下层提供按 id 标记的能力
        if not notification_ids:
            raise ValueError('至少需要一个通知ID')
        results = []
        for nid in notification_ids:
            results.append(DomainNotificationService.mark_as_read(nid, user_id))
        return results

    @staticmethod
    def get_unread_count(user_id: int):
        # 直接计数模型以保证简单性
        count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
        return {'unread_count': count}


