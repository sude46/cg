from typing import Any

from app.common.database import get_read_session, pagination_utils, utcnow
from app.notifications.models import Notification
from core import db
from core.metrics import monitor_db


class NotificationRepository:

    @staticmethod
    def _read_session():
        return get_read_session()

    @staticmethod
    @monitor_db("insert", "notifications")
    def create_notification(data: dict[str, Any]) -> Notification:
        notif = Notification(**data)
        db.session.add(notif)
        return notif

    @staticmethod
    @monitor_db("select", "notifications")
    def get_by_id(notification_id: int, user_id: int, force_master: bool = False) -> Notification | None:
        session = db.session if force_master else NotificationRepository._read_session()
        return session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.id == notification_id,
            Notification.deleted_at.is_(None)
        ).first()

    @staticmethod
    @monitor_db("select", "notifications")
    def list_by_user(user_id: int, page: int = 1, per_page: int = 20, unread_only: bool = False):
        session = NotificationRepository._read_session()
        query = session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.deleted_at.is_(None)
        )
        if unread_only:
            query = query.filter(Notification.is_read.is_(False))
        query = query.order_by(Notification.created_at.desc())
        result = pagination_utils.paginate(query, page=page, per_page=per_page)
        return {
            'items': result['items'],
            'pagination': result['pagination']
        }

    @staticmethod
    @monitor_db("update", "notifications")
    def mark_as_read(notification: Notification) -> None:
        notification.is_read = True
        db.session.add(notification)

    @staticmethod
    @monitor_db("update", "notifications")
    def mark_all_as_read(user_id: int) -> None:
        db.session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
            Notification.deleted_at.is_(None)
        ).update(
            {Notification.is_read: True},
            synchronize_session=False
        )

    @staticmethod
    @monitor_db("update", "notifications")
    def delete(notification: Notification) -> None:
        """软删除通知"""
        notification.deleted_at = utcnow()
        db.session.add(notification)

    @staticmethod
    @monitor_db("count", "notifications")
    def count_unread(user_id: int, force_master: bool = False) -> int:
        """统计用户未读通知数"""
        session = db.session if force_master else NotificationRepository._read_session()
        return session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
            Notification.deleted_at.is_(None)
        ).count()


notification_repository = NotificationRepository()
