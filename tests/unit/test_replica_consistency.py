"""FIX-13: 关键计数/阈值判定强行走主库，避免主从延迟造成短时错误。"""

from app.follows.services import FollowService
from tests.unit.factories import PostFactory, UserFactory


def test_get_unread_count_recently_modified_forces_master(
    app, db_session, mock_redis, monkeypatch
):
    from app.notifications import services as notif_services
    from app.notifications.cache import NotificationCache
    from app.notifications.services import NotificationService

    with app.app_context():
        user = UserFactory()
        NotificationCache.set_unread_count(user.id, 5)
        NotificationCache.mark_recently_modified(user.id, ttl=60)

        calls = []

        def count_unread(user_id, force_master=False):
            calls.append(force_master)
            return 7

        monkeypatch.setattr(
            notif_services.notification_repository, 'count_unread', count_unread
        )

        assert NotificationService.get_unread_count(user.id) == 7
        assert calls == [True]


def test_follow_repository_follower_count_force_master(
    app, db_session, monkeypatch
):
    from app.follows.repositories import follow_repository

    with app.app_context():
        user = UserFactory()
        monkeypatch.setattr(
            follow_repository,
            '_read_session',
            lambda: (_ for _ in ()).throw(AssertionError('read replica used')),
        )

        assert follow_repository.get_follower_count(user.id, force_master=True) == 0


def test_publish_post_uses_master_follower_count(
    app, db_session, mock_redis, monkeypatch
):
    from app.feeds.services import FeedService
    from app.follows.repositories import follow_repository

    with app.app_context():
        author = UserFactory()
        follower = UserFactory()
        FollowService.follow_user(follower.id, author.id)

        calls = []
        original = follow_repository.get_follower_count

        def wrapper(followed_id, force_master=False):
            calls.append(force_master)
            return original(followed_id, force_master=force_master)

        monkeypatch.setattr(follow_repository, 'get_follower_count', wrapper)

        FeedService.publish_post(123, author.id, 1719820800)

        assert calls and calls[0] is True


def test_comment_list_top_by_likes_force_master(app, db_session, monkeypatch):
    from app.comments.repositories import comment_repository

    with app.app_context():
        post = PostFactory()
        monkeypatch.setattr(
            comment_repository,
            '_read_session',
            lambda: (_ for _ in ()).throw(AssertionError('read replica used')),
        )

        assert comment_repository.list_top_by_likes(
            post.id, limit=10, force_master=True
        ) == []
