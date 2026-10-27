"""FIX-03: 事件生产端 outbox，业务提交与事件入队同事务。"""

from app.comments.services import CommentService
from app.common.outbox import EventOutbox, enqueue_event
from app.follows.services import FollowService
from app.posts.services import PostService
from core import db
from tasks.outbox_tasks import relay_event_outbox
from tests.unit.factories import PostFactory, UserFactory


def _outbox_rows(event_name):
    return db.session.query(EventOutbox).filter_by(event_name=event_name).all()


def _forbid_direct_publish(monkeypatch):
    from app.common.events import event_bus

    calls = []
    monkeypatch.setattr(
        event_bus,
        'publish',
        lambda *args, **kwargs: calls.append(args) or True,
    )
    return calls


def test_post_create_enqueues_outbox_not_direct_publish(
    app, db_session, mock_redis, monkeypatch
):
    with app.app_context():
        calls = _forbid_direct_publish(monkeypatch)
        user = UserFactory()

        post = PostService.create_post(user.id, 'outbox post')

        rows = _outbox_rows('post.created')
        assert len(rows) == 1
        assert rows[0].payload['id'] == post.id
        assert rows[0].status == 'pending'
        assert calls == []


def test_comment_create_enqueues_outbox_not_direct_publish(
    app, db_session, mock_redis, monkeypatch
):
    with app.app_context():
        calls = _forbid_direct_publish(monkeypatch)
        author = UserFactory()
        commenter = UserFactory()
        post = PostFactory(author=author)

        CommentService.create_comment(
            commenter.id, {'post_id': post.id, 'content': 'outbox comment'}
        )

        assert len(_outbox_rows('comment.created')) == 1
        assert len(_outbox_rows('post.comment_count_changed')) == 1
        assert calls == []


def test_follow_enqueues_outbox_not_direct_publish(
    app, db_session, mock_redis, monkeypatch
):
    with app.app_context():
        calls = _forbid_direct_publish(monkeypatch)
        follower = UserFactory()
        followed = UserFactory()

        FollowService.follow_user(follower.id, followed.id)

        rows = _outbox_rows('follow.created')
        assert len(rows) == 1
        assert rows[0].payload['actor_id'] == follower.id
        assert rows[0].payload['user_id'] == followed.id
        assert calls == []


def test_relay_marks_sent_with_same_event_id(
    app, db_session, mock_redis, monkeypatch
):
    from app.common.events import event_bus

    with app.app_context():
        event_id = enqueue_event('post.created', {'id': 1, 'content': 'x'})
        db.session.commit()

        captured = {}
        monkeypatch.setattr(
            event_bus,
            'publish',
            lambda name, payload, event_id=None: captured.update(
                {'name': name, 'payload': payload, 'event_id': event_id}
            )
            or True,
        )

        relay_event_outbox()

        row = db.session.query(EventOutbox).filter_by(event_id=event_id).one()
        assert row.status == 'sent'
        assert row.sent_at is not None
        assert captured['event_id'] == event_id
        assert captured['name'] == 'post.created'


def test_relay_keeps_pending_on_publish_failure(
    app, db_session, mock_redis, monkeypatch
):
    from app.common.events import event_bus

    with app.app_context():
        event_id = enqueue_event('post.created', {'id': 2})
        db.session.commit()

        monkeypatch.setattr(
            event_bus, 'publish', lambda *args, **kwargs: False
        )

        relay_event_outbox()

        row = db.session.query(EventOutbox).filter_by(event_id=event_id).one()
        assert row.status == 'pending'
        assert row.retry_count == 1
        assert row.next_retry_at is not None
