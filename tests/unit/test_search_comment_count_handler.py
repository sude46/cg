"""FIX-07: 无订阅者事件不再产生死信噪音；评论数变化要有 ES 消费者。"""

from tests.unit.factories import CommentFactory, UserFactory


def test_on_post_comment_count_changed_updates_es(app, monkeypatch):
    from services.search import event_handlers

    captured = {}

    monkeypatch.setattr(event_handlers.es_client, 'is_available', lambda: True)

    def update_post(post_id, **fields):
        captured['post_id'] = post_id
        captured['fields'] = fields
        return True

    monkeypatch.setattr(
        event_handlers.PostSearchService, 'update_post', staticmethod(update_post)
    )

    with app.app_context():
        event_handlers.on_post_comment_count_changed(
            {'post_id': 123, 'comment_count': 7}
        )

    assert captured['post_id'] == 123
    assert captured['fields'] == {'comment_count': 7}


def test_on_post_comment_count_changed_marks_dirty_on_failure(app, monkeypatch):
    from services.search import event_handlers

    marked = []
    monkeypatch.setattr(event_handlers.es_client, 'is_available', lambda: True)
    monkeypatch.setattr(
        event_handlers.PostSearchService,
        'update_post',
        staticmethod(lambda *_args, **_kwargs: False),
    )
    monkeypatch.setattr(
        event_handlers.PostSearchService,
        'mark_dirty',
        staticmethod(lambda post_id: marked.append(post_id)),
    )

    with app.app_context():
        event_handlers.on_post_comment_count_changed(
            {'post_id': 123, 'comment_count': 7}
        )

    assert marked == [123]


def test_comment_unlike_does_not_publish_unsubscribed_event(
    app, db_session, mock_redis, monkeypatch
):
    from app.common.events import event_bus
    from app.likes.services import LikeService

    with app.app_context():
        user = UserFactory()
        comment = CommentFactory()
        LikeService.create_like(user_id=user.id, comment_id=comment.id)

        published = []
        monkeypatch.setattr(
            event_bus,
            'publish',
            lambda name, payload: published.append(name) or True,
        )

        LikeService.delete_like(user_id=user.id, comment_id=comment.id)

        assert 'comment.like_count_changed' not in published
