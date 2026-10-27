"""FIX-08: 通知按 event_id 幂等，重试/重复投递不能产生重复通知。"""

from app.notifications.models import Notification
from app.notifications.services import NotificationService, _handle_comment_created
from tests.unit.factories import UserFactory


def test_create_notification_is_idempotent_by_event_id(app, db_session, mock_redis):
    from app.notifications.cache import NotificationCache

    with app.app_context():
        user = UserFactory()
        actor = UserFactory()
        NotificationCache.set_unread_count(user.id, 0)

        data = {
            "user_id": user.id,
            "actor_id": actor.id,
            "type": "comment",
            "comment_id": 1,
            "resource_id": 1,
            "resource_type": "comment",
            "content": "有人评论了你的帖子",
            "event_id": "evt-comment-1",
        }

        first = NotificationService.create_notification(dict(data))
        second = NotificationService.create_notification(dict(data))

        assert second["id"] == first["id"]
        assert Notification.query.filter_by(event_id="evt-comment-1").count() == 1
        # 重复事件不能把未读数加两次
        assert NotificationCache.get_unread_count(user.id) == 1


def test_notification_handler_passes_event_id(app, db_session, mock_redis):
    with app.app_context():
        user = UserFactory()
        actor = UserFactory()
        payload = {
            "user_id": user.id,
            "actor_id": actor.id,
            "type": "comment",
            "comment_id": 1,
            "content": "测试评论通知",
            "_event_id": "evt-handler-1",
        }

        _handle_comment_created(dict(payload))
        _handle_comment_created(dict(payload))

        assert Notification.query.filter_by(event_id="evt-handler-1").count() == 1


def test_dispatch_injects_event_id_into_handler_payload(app, mock_redis):
    from app.common.events import event_bus

    seen = {}

    def handler(payload):
        seen.update(payload)

    event_bus._subscribers['t.inject'] = [handler]
    try:
        with app.app_context():
            payload = {"a": 1}
            event = {
                "id": "evt-bus-1",
                "event": "t.inject",
                "payload": payload,
                "retry_count": 0,
            }
            event_bus._dispatch(mock_redis, "t.inject", payload, event)

        assert seen["_event_id"] == "evt-bus-1"
        assert seen["a"] == 1
    finally:
        event_bus._subscribers.pop('t.inject', None)
