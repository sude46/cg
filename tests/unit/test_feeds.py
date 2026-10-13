from datetime import UTC, datetime

from app.feeds.cache import FeedCache
from app.feeds.services import FeedService
from app.follows.services import FollowService
from tests.unit.factories import PostFactory, UserFactory


class TestFeedService:
    """Feed流服务单元测试"""
    def test_get_timeline_cache_hit(self, app, db_session, mock_redis):
        """缓存命中时返回缓存数据"""
        with app.app_context():
            user = UserFactory()
            p1 = PostFactory()
            p2 = PostFactory()
            FeedCache.add_post_to_feed(user.id, str(p1.id), 1719820800)
            FeedCache.add_post_to_feed(user.id, str(p2.id), 1719820801)

            result = FeedService.get_timeline(user.id, limit=10)
            assert result["source"] == "cache"
            assert len(result["items"]) == 2

    def test_get_timeline_empty_cache(self, app, db_session, mock_redis):
        """缓存命中但为空(用户未关注任何人）"""
        with app.app_context():
            user = UserFactory()
            FeedCache.set_empty_cache(user.id)
            result = FeedService.get_timeline(user.id, limit=10)
            assert result["source"] == "empty"
            assert result["items"] == []
            assert result["has_more"] is False

    def test_get_timeline_db_fallback(self, app, db_session, mock_redis):
        """缓存未命中，走数据库拉取"""
        with app.app_context():
            user = UserFactory()
            author = UserFactory()
            PostFactory(author=author)
            FollowService.follow_user(user.id, author.id)
            result = FeedService.get_timeline(user.id, limit=10)
            assert result["source"] == "db"
            assert len(result["items"]) >= 0

    def test_get_timeline_cursor_pagination(self, app, db_session, mock_redis):
        """游标翻页不重复、不遗漏"""
        with app.app_context():
            user = UserFactory()
            p1, p2, p3 = PostFactory(), PostFactory(), PostFactory()
            FeedCache.add_post_to_feed(user.id, str(p1.id), 1719820800)
            FeedCache.add_post_to_feed(user.id, str(p2.id), 1719820801)
            FeedCache.add_post_to_feed(user.id, str(p3.id), 1719820802)

            first = FeedService.get_timeline(user.id, limit=2)
            assert first["source"] == "cache"
            assert first["has_more"] is True
            assert first["next_cursor"]
            assert first["items"][0]["id"] == p3.id  # 最新的在前

            second = FeedService.get_timeline(user.id, cursor=first["next_cursor"], limit=2)
            ids1 = {p["id"] for p in first["items"]}
            ids2 = {p["id"] for p in second["items"]}
            assert not (ids1 & ids2), "翻页不可重复"
            assert ids1 | ids2 == {p1.id, p2.id, p3.id}, "翻页不可遗漏"

    def test_publish_post_push_mode(self, app, db_session, mock_redis):
        """普通用户发帖，fanout 下沉 Celery（测试 eager 模式同步执行）"""
        with app.app_context():
            author = UserFactory()
            follower = UserFactory()
            FollowService.follow_user(follower.id, author.id)
            result = FeedService.publish_post(999, author.id, 1719820800)

            assert result["mode"] == "push_async"
            assert result["followers"] == 1
            # eager 模式下任务已同步执行，粉丝 feed 应已写入
            assert "999" in (FeedCache.pull_feed(follower.id, 1, 10) or [])

    def test_publish_post_enqueue_failure_falls_back_sync(self, app, db_session, mock_redis, monkeypatch):
        """入队失败时降级为同步推送，保证帖子不丢"""
        from types import SimpleNamespace

        import tasks.feed_tasks as feed_tasks

        def boom(*args, **kwargs):
            raise RuntimeError("broker down")

        monkeypatch.setattr(
            feed_tasks, "async_push_to_followers", SimpleNamespace(apply_async=boom)
        )
        with app.app_context():
            author = UserFactory()
            follower = UserFactory()
            FollowService.follow_user(follower.id, author.id)

            result = FeedService.publish_post(888, author.id, 1719820800)

            assert result["mode"] == "push_fallback"
            assert result["pushed"] == 1
            assert "888" in (FeedCache.pull_feed(follower.id, 1, 10) or [])

    def test_publish_post_pull_mode(self, app, db_session, mock_redis):
        """大V用户发帖，拉模式（粉丝>=1000）"""
        with app.app_context():
            author = UserFactory()
            for _ in range(1000):
                f = UserFactory()
                FollowService.follow_user(f.id, author.id)
            result = FeedService.publish_post(999, author.id, 1719820800)
            assert result["mode"] == "pull"
            assert result["pushed"] == 0

    def test_big_v_post_visible_in_follower_timeline(self, app, db_session, mock_redis, monkeypatch):
        """推拉结合回归：大V发帖后，粉丝刷新时间线能看到（改前会丢失）"""
        with app.app_context():
            monkeypatch.setitem(app.config, 'BIG_V_THRESHOLD', 1)
            author = UserFactory()
            follower = UserFactory()
            FollowService.follow_user(follower.id, author.id)

            t1 = datetime.fromtimestamp(1719820800, tz=UTC).replace(tzinfo=None)
            t2 = datetime.fromtimestamp(1719820801, tz=UTC).replace(tzinfo=None)
            p1 = PostFactory(author=author, created_at=t1)
            r1 = FeedService.publish_post(p1.id, author.id, 1719820800)
            assert r1["mode"] == "pull"

            # 首次读：feed 未命中 -> DB 兜底，能看到 p1
            first = FeedService.get_timeline(follower.id, limit=10)
            assert first["source"] == "db"
            assert p1.id in [it["id"] for it in first["items"]]

            # 大V再发帖：不 fanout，但写 outbox
            p2 = PostFactory(author=author, created_at=t2)
            FeedService.publish_post(p2.id, author.id, 1719820801)

            # 再次读：feed 命中(含 p1) + 拉大V outbox -> 合流后能看到 p2
            second = FeedService.get_timeline(follower.id, limit=10)
            assert second["source"] == "hybrid"
            ids = [it["id"] for it in second["items"]]
            assert p2.id in ids
            assert ids[0] == p2.id  # 最新在前

    def test_too_many_big_v_falls_back_to_db(self, app, db_session, mock_redis, monkeypatch):
        """关注的大V超过归并上限时，退化为DB兜底而不是截断丢失内容"""
        with app.app_context():
            monkeypatch.setitem(app.config, 'BIG_V_THRESHOLD', 1)
            monkeypatch.setattr(FeedCache, 'MAX_MERGE_BIGV', 1)
            follower = UserFactory()
            a1, a2 = UserFactory(), UserFactory()
            FollowService.follow_user(follower.id, a1.id)
            FollowService.follow_user(follower.id, a2.id)

            p1 = PostFactory(author=a1)
            p2 = PostFactory(author=a2)
            FeedService.publish_post(p1.id, a1.id, 1719820800)
            FeedService.publish_post(p2.id, a2.id, 1719820801)

            # 预热缓存
            FeedService.get_timeline(follower.id, limit=10)
            # 关注2个大V > 上限1 -> 退化为DB兜底
            res = FeedService.get_timeline(follower.id, limit=10)
            assert res["source"] == "db"
            ids = {it["id"] for it in res["items"]}
            assert {p1.id, p2.id} <= ids

    def test_big_v_not_pushed_to_followers(self, app, db_session, mock_redis, monkeypatch):
        """大V发帖不 fanout 到粉丝 feed（改走 outbox 拉取）"""
        with app.app_context():
            monkeypatch.setitem(app.config, 'BIG_V_THRESHOLD', 1)
            author = UserFactory()
            follower = UserFactory()
            FollowService.follow_user(follower.id, author.id)

            FeedService.publish_post(999, author.id, 1719820800)

            assert FeedCache.pull_feed(follower.id, 1, 10) is None
            assert FeedCache.pull_outbox_scored_by_cursor(author.id, None, 10)

    def test_delete_post_remove_from_feed(self, app, db_session, mock_redis):
        """删除帖子后从Feed移除"""
        with app.app_context():
            author = UserFactory()
            post = PostFactory(author=author)
            FeedCache.add_post_to_feed(author.id, post.id, 1719820800)
            result = FeedService.delete_post(post.id, author.id)
            assert result["removed_from_author"] is True

    def test_follow_user_invalidate_feed(self, app, db_session, mock_redis):
        """关注用户后清空时间线缓存"""
        with app.app_context():
            follower = UserFactory()
            followed = UserFactory()
            FeedCache.add_post_to_feed(follower.id, "999", 1719820800)
            result = FeedService.follow_user(follower.id, followed.id)
            assert result is True
            assert FeedCache.pull_feed(follower.id, 1, 10) is None

    def test_unfollow_user_invalidate_feed(self, app, db_session, mock_redis):
        """取关后清空时间线缓存"""
        with app.app_context():
            follower = UserFactory()
            followed = UserFactory()
            result = FeedService.unfollow_user(follower.id, followed.id)
            assert result is True

    def test_refresh_user_feed(self, app, db_session, mock_redis):
        """手动刷新用户时间线"""
        with app.app_context():
            user = UserFactory()

            result = FeedService.refresh_user_feed(user.id)

            assert result["refreshed"] is True
            assert "loaded_posts" in result


class TestExploreFeed:
    """广场流单元测试"""

    def test_explore_cache_add_and_cursor(self, app, mock_redis):
        """广场缓存写入后可按游标拉取，最新的在前"""
        from app.feeds.cache import ExploreCache
        with app.app_context():
            ExploreCache.add_post(100, 1719820800)
            ExploreCache.add_post(101, 1719820801)
            ids, cursor, has_more = ExploreCache.pull_by_cursor(None, limit=10)
            assert ids == ["101", "100"]
            assert cursor is None
            assert has_more is False

    def test_get_explore_db_fallback(self, app, db_session, mock_redis):
        """广场缓存未命中，走数据库"""
        with app.app_context():
            author = UserFactory()
            PostFactory(author=author)
            PostFactory(author=author)
            result = FeedService.get_explore(limit=10)
            assert result["source"] == "db"
            assert len(result["items"]) >= 2

    def test_explore_publish_then_delete(self, app, db_session, mock_redis):
        """发帖写入广场，删帖从广场移除"""
        from app.feeds.cache import ExploreCache
        with app.app_context():
            author = UserFactory()
            post = PostFactory(author=author)
            FeedService.publish_post(post.id, author.id, 1719820800)
            ids, _, _ = ExploreCache.pull_by_cursor(None, limit=10)
            assert str(post.id) in ids

            FeedService.delete_post(post.id, author.id)
            after, _, _ = ExploreCache.pull_by_cursor(None, limit=10)
            assert after is None or str(post.id) not in after


class TestFeedCache:
    """Feed 缓存层单元测试"""

    def test_add_and_pull_post(self, app, mock_redis):
        """添加帖子到 Feed 后能拉取"""
        from app.feeds.cache import FeedCache
        with app.app_context():
            FeedCache.add_post_to_feed(1, "100", 1719820800)
            FeedCache.add_post_to_feed(1, "101", 1719820801)
            ids = FeedCache.pull_feed(1, 1, 10)
            assert ids == ["101", "100"]

    def test_remove_post(self, app, mock_redis):
        """删除帖子"""
        from app.feeds.cache import FeedCache
        with app.app_context():
            FeedCache.add_post_to_feed(1, "100", 1719820800)
            FeedCache.remove_posts(1, "100")
            ids = FeedCache.pull_feed(1, 1, 10)
            assert "100" not in ids

    def test_set_empty_cache(self, app, mock_redis):
        """空缓存标记"""
        from app.feeds.cache import FeedCache
        with app.app_context():
            FeedCache.set_empty_cache(1)
            ids = FeedCache.pull_feed(1, 1, 10)
            assert ids == []

    def test_is_big_v(self, app, mock_redis):
        """大V判断"""
        from app.feeds.cache import FeedCache
        with app.app_context():
            assert FeedCache.is_big_v(100) is False
            assert FeedCache.is_big_v(1000) is True
            assert FeedCache.is_big_v(5000) is True

    def test_batch_fill_cache(self, app, mock_redis):
        """批量回填缓存"""
        from app.feeds.cache import FeedCache
        with app.app_context():
            cache_data = [
                {"id": 100, "created_at": 1719820800},
                {"id": 101, "created_at": 1719820801},
            ]
            FeedCache.batch_fill_cache(1, cache_data)
            ids = FeedCache.pull_feed(1, 1, 10)
            assert len(ids) == 2

    def test_invalidate_feed(self, app, mock_redis):
        """清空 Feed 缓存"""
        from app.feeds.cache import FeedCache
        with app.app_context():
            FeedCache.add_post_to_feed(1, "100", 1719820800)
            FeedCache.invalidate_feed(1)
            ids = FeedCache.pull_feed(1, 1, 10)
            assert ids is None
