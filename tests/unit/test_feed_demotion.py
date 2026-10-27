"""FIX-10: 大V降级时把历史帖子补推给粉丝，不能只切换标记。"""

from app.feeds.cache import FeedCache
from app.feeds.services import FeedService
from app.follows.services import FollowService
from tests.unit.factories import PostFactory, UserFactory


def test_demoted_bigv_backfills_history(app, db_session, mock_redis, monkeypatch):
    monkeypatch.setitem(app.config, 'BIG_V_THRESHOLD', 1)
    with app.app_context():
        author = UserFactory()
        follower = UserFactory()
        FollowService.follow_user(follower.id, author.id)

        p1 = PostFactory(author=author)
        r1 = FeedService.publish_post(p1.id, author.id, 1719820800)
        assert r1['mode'] == 'pull'

        # 大V期间不 fanout，粉丝 feed 里没有 p1
        cached = FeedCache.pull_feed(follower.id, 1, 10) or []
        assert str(p1.id) not in cached

        # 粉丝数掉到阈值以下：下一篇帖子触发降级回填
        monkeypatch.setitem(app.config, 'BIG_V_THRESHOLD', 2)
        p2 = PostFactory(author=author)
        r2 = FeedService.publish_post(p2.id, author.id, 1719820801)
        assert r2['mode'] != 'pull'

        ids = FeedCache.pull_feed(follower.id, 1, 10) or []
        assert str(p1.id) in ids, '降级后历史帖子必须补推给粉丝'
        assert str(p2.id) in ids
        assert FeedCache.filter_big_v([author.id]) == []


def test_demotion_backfill_enqueue_failure_keeps_pull_mode(
    app, db_session, mock_redis, monkeypatch
):
    monkeypatch.setitem(app.config, 'BIG_V_THRESHOLD', 1)
    with app.app_context():
        author = UserFactory()
        follower = UserFactory()
        FollowService.follow_user(follower.id, author.id)

        p1 = PostFactory(author=author)
        FeedService.publish_post(p1.id, author.id, 1719820800)

        import tasks.feed_tasks as feed_tasks

        def boom(*args, **kwargs):
            raise RuntimeError('broker down')

        monkeypatch.setitem(app.config, 'BIG_V_THRESHOLD', 2)
        monkeypatch.setattr(feed_tasks.backfill_demoted_author, 'apply_async', boom)

        p2 = PostFactory(author=author)
        result = FeedService.publish_post(p2.id, author.id, 1719820801)

        # 回填入队失败：保留大V标记、继续拉模式，历史内容不丢
        assert result['mode'] == 'pull'
        assert FeedCache.filter_big_v([author.id]) == [author.id]
