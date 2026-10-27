"""FIX-06: 异步 handler 不能吞异常，否则事件总线不会重试。"""

import pytest


@pytest.mark.parametrize(
    "handler_name,payload",
    [
        ("_handle_comment_created", {"user_id": 1, "actor_id": 2, "type": "comment"}),
        ("_handle_like_created", {"user_id": 1, "actor_id": 2, "type": "like"}),
        ("_handle_follow_created", {"user_id": 1, "actor_id": 2, "type": "follow"}),
    ],
)
def test_notification_handlers_propagate_failure(
    app, mock_redis, monkeypatch, handler_name, payload
):
    from app.notifications import services as notif_services

    def boom(_data):
        raise RuntimeError("notification db down")

    monkeypatch.setattr(
        notif_services.NotificationService,
        "create_notification",
        staticmethod(boom),
    )
    handler = getattr(notif_services, handler_name)

    with app.app_context(), pytest.raises(RuntimeError, match="notification db down"):
        handler(payload)


def test_feed_delete_handler_propagates_failure(app, mock_redis, monkeypatch):
    from app.feeds import handlers as feed_handlers

    def boom(**_kwargs):
        raise RuntimeError("feed cleanup failed")

    monkeypatch.setattr(
        feed_handlers.FeedService,
        "delete_post",
        staticmethod(boom),
    )

    with app.app_context(), pytest.raises(RuntimeError, match="feed cleanup failed"):
        feed_handlers.on_post_deleted({"post_id": 1, "user_id": 2})
