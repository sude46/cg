from typing import Optional, Dict, Any
from datetime import datetime, timezone
from app.common.database import utcnow
from core import db
from app.notifications.models import Notification
from app.common.database import pagination_utils, get_read_session


class NotificationRepository:

    @staticmethod
    def _read_session():
        return get_read_session()

    @staticmethod
    def create_notification(data: Dict[str, Any]) -> Notification:
        notif = Notification(**data)
        db.session.add(notif)
        return notif

    @staticmethod
    def get_by_id(notification_id: int, user_id: int, force_master: bool = False) -> Optional[Notification]:
        session = db.session if force_master else NotificationRepository._read_session()
        return session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.id == notification_id,
            Notification.deleted_at.is_(None)
        ).first()

    @staticmethod
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
    def mark_as_read(notification: Notification) -> None:
        notification.is_read = True
        db.session.add(notification)

    @staticmethod
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
    def delete(notification: Notification) -> None:
        """软删除通知"""
        notification.deleted_at = utcnow()
        db.session.add(notification)

    @staticmethod
    def count_unread(user_id: int, force_master: bool = False) -> int:
        """统计用户未读通知数"""
        session = db.session if force_master else NotificationRepository._read_session()
        return session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
            Notification.deleted_at.is_(None)
        ).count()


notification_repository = NotificationRepository()
