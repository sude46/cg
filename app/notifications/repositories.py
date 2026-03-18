from typing import Optional, Dict, Any
from sqlalchemy.orm import selectinload, joinedload
from core import db
from app.notifications.models import Notification
from app.common.database import pagination_utils


class NotificationRepository:
    @staticmethod
    def create_notification(data: Dict[str, Any]) -> Notification:
        notif = Notification(**data)
        db.session.add(notif)
        return notif

    @staticmethod
    def get_by_id(notification_id: int, user_id: int) -> Optional[Notification]:
        return Notification.query.filter_by(user_id=user_id, id=notification_id).first()

    @staticmethod
    def list_by_user(user_id: int, page: int = 1, per_page: int = 20, unread_only: bool = False):
        query = Notification.query.filter_by(user_id=user_id)
        if unread_only:
            query = query.filter_by(is_read=False)
        return pagination_utils.paginate(query.order_by(Notification.created_at.desc()), page=page, per_page=per_page)

    @staticmethod
    def mark_as_read(notification: Notification) -> None:
        notification.is_read = True
        db.session.add(notification)

    @staticmethod
    def mark_all_as_read(user_id: int) -> None:
        Notification.query.filter_by(user_id=user_id, is_read=False).update({Notification.is_read: True})

    @staticmethod
    def delete(notification: Notification) -> None:
        db.session.delete(notification)


notification_repository = NotificationRepository()
