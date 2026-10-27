"""FIX-02: 关注缓存 miss / 大V索引丢失时，不能静默丢掉大V内容。"""

from datetime import UTC, datetime

from app.feeds.cache import FeedCache
from app.feeds.services import FeedService
from app.follows.services import FollowService
from core.redis_cache import redis_cache
from tests.unit.factories import PostFactory, UserFactory


def _seed_big_v_timeline(app, monkeypatch):
    """建立大V + 粉丝，先读一次让 feed 缓存命中，再返回 (follower, author, p1)。"""
    monkeypatch.setitem(app.config, 'BIG_V_THRESHOLD', 1)
    author = UserFactory()
    follower = UserFactory()
    FollowService.follow_user(follower.id, author.id)

    t1 = datetime.fromtimestamp(1719820800, tz=UTC).replace(tzinfo=None)
    p1 = PostFactory(author=author, created_at=t1)
    FeedService.publish_post(p1.id, author.id, 1719820800)

    first = FeedService.get_timeline(follower.id, limit=10)
    assert first["source"] == "db"
    assert p1.id in [item["id"] for item in first["items"]]
    return follower, author, p1


def test_timeline_keeps_bigv_when_following_cache_missing(
    app, db_session, mock_redis, monkeypatch
):
    """following:{uid} 被淘汰后，feed 命中时仍应拉大V outbox。"""
    with app.app_context():
        follower, author, _p1 = _seed_big_v_timeline(app, monkeypatch)

        # 模拟 Redis 淘汰关注列表；feed:bigv 仍在
        redis_cache.delete(f"following:{follower.id}")

        t2 = datetime.fromtimestamp(1719820801, tz=UTC).replace(tzinfo=None)
        p2 = PostFactory(author=author, created_at=t2)
        FeedService.publish_post(p2.id, author.id, 1719820801)

        second = FeedService.get_timeline(follower.id, limit=10)

        ids = [item["id"] for item in second["items"]]
        assert p2.id in ids, "following 缓存 miss 不能导致新的大V帖子消失"


def test_following_cache_distinguishes_missing_and_empty(app, mock_redis):
    """缓存 miss 返回 None；确认没关注才返回 []，空标记在关注后要失效。"""
    from app.follows.cache import FollowCache

    with app.app_context():
        assert FollowCache.get_following_ids(123) is None

        FollowCache.set_empty_following(123)
        assert FollowCache.get_following_ids(123) == []

        FollowCache.preload_following(123, [1, 2])
        assert set(FollowCache.get_following_ids(123)) == {1, 2}

        redis_cache.delete("following:123")
        FollowCache.set_empty_following(123)
        FollowCache.add_relation(123, 9)
        assert set(FollowCache.get_following_ids(123)) == {9}


def test_timeline_keeps_bigv_when_bigv_index_missing(
    app, db_session, mock_redis, monkeypatch
):
    """feed:bigv 被淘汰后，应 fail-open 拉取关注对象 outbox，而不是静默丢内容。"""
    with app.app_context():
        follower, author, _p1 = _seed_big_v_timeline(app, monkeypatch)

        t2 = datetime.fromtimestamp(1719820801, tz=UTC).replace(tzinfo=None)
        p2 = PostFactory(author=author, created_at=t2)
        FeedService.publish_post(p2.id, author.id, 1719820801)

        # 模拟 Redis 在发帖后淘汰大V索引；following 仍在
        redis_cache.delete(FeedCache.BIGV_SET_KEY)

        second = FeedService.get_timeline(follower.id, limit=10)

        ids = [item["id"] for item in second["items"]]
        assert p2.id in ids, "feed:bigv 丢失时不能静默丢掉大V内容"
