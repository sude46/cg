

class TestPostTasks:
    """帖子相关Celery任务单元测试"""

    def test_delayed_invalidate_post(self, app, mock_redis):
        from app.posts.cache import PostCache
        from tasks.post_tasks import delayed_invalidate
        with app.app_context():
            PostCache.set(1, {"id": 1})
            result = delayed_invalidate(1)
            assert result["status"] == "success"
            assert PostCache.get(1) is None

    def test_delayed_invalidate_comment(self, app, mock_redis):
        from app.comments.cache import CommentCache
        from tasks.post_tasks import delayed_invalidate_comment
        with app.app_context():
            CommentCache.set(1, {"id": 1})
            result = delayed_invalidate_comment(1)
            assert result["status"] == "success"
            assert CommentCache.get(1) is None


class TestUserTasks:
    """用户相关Celery任务单元测试"""

    def test_delayed_invalidate_user_cache(self, app, mock_redis):
        from app.users.cache import UserCache
        from tasks.user_tasks import delayed_invalidate
        with app.app_context():
            UserCache.set_profile(1, {"id": 1, "username": "test"})
            UserCache.set_by_username("test", 1)
            result = delayed_invalidate(1, username="test", email="test@test.com")
            assert result["status"] == "success"
            assert UserCache.get_profile(1) is None
            assert UserCache.get_by_username("test") is None


class TestFeedTasks:
    """Feed流相关Celery任务单元测试"""

    def test_async_invalidate_user_feed(self, app, mock_redis):
        from app.feeds.cache import FeedCache
        from tasks.feed_tasks import async_invalidate_user_feed
        with app.app_context():
            FeedCache.add_post_to_feed(1, "100", 1719820800)
            result = async_invalidate_user_feed(1)
            assert result["invalidated"] is True
            assert FeedCache.pull_feed(1, 1, 10) is None

    def test_async_push_to_followers(self, app, db_session, mock_redis):
        from app.feeds.cache import FeedCache
        from app.follows.services import FollowService
        from tasks.feed_tasks import async_push_to_followers
        from tests.unit.factories import UserFactory
        with app.app_context():
            author = UserFactory()
            follower = UserFactory()
            FollowService.follow_user(follower.id, author.id)

            result = async_push_to_followers(100, author.id, 1719820800)

            assert result["pushed"] == 1
            assert "100" in (FeedCache.pull_feed(follower.id, 1, 10) or [])

    def test_async_remove_post_from_followers(self, app, mock_redis):
        from app.feeds.cache import FeedCache
        from tasks.feed_tasks import async_remove_post_from_followers
        with app.app_context():
            FeedCache.add_post_to_feed(1, "100", 1719820800)
            result = async_remove_post_from_followers(100, [1])
            assert result["status"] == "success"


class TestSearchTasks:
    """搜索索引同步/对账任务单元测试"""

    def test_reconcile_search_index_reindexes_dirty_post(self, app, db_session, mock_redis, monkeypatch):
        from core.redis_cache import redis_cache
        from services.search import PostSearchService
        from tasks.search_reconcile import reconcile_search_index
        from tests.unit.factories import PostFactory

        captured = {}
        monkeypatch.setattr(
            PostSearchService, 'index_post',
            lambda doc: captured.setdefault('doc', doc) or True
        )
        with app.app_context():
            post = PostFactory()
            redis_cache.sadd(PostSearchService.DIRTY_KEY, post.id)

            result = reconcile_search_index(batch_size=10)

            assert result['status'] == 'success'
            assert result['fixed'] == 1
            assert captured['doc']['id'] == post.id
            assert post.id not in redis_cache.smembers(PostSearchService.DIRTY_KEY, for_write=True)

    def test_on_post_deleted_marks_dirty_when_sync_fails(self, app, mock_redis, monkeypatch):
        from core.redis_cache import redis_cache
        from services.search import PostSearchService, event_handlers

        monkeypatch.setattr(PostSearchService, 'delete_post', classmethod(lambda cls, pid: False))
        with app.app_context():
            event_handlers.on_post_deleted({'post_id': 123})

            assert 123 in redis_cache.smembers(PostSearchService.DIRTY_KEY, for_write=True)


class TestLikeTasks:
    """点赞相关Celery任务单元测试"""

    def test_async_like_create(self, app, db_session, mock_redis):
        from tasks.like_tasks import async_like_to_do
        from tests.unit.factories import PostFactory, UserFactory
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            result = async_like_to_do(user.id, "post", post.id, "create", "test_pending")
            assert result["status"] == "success"

    def test_async_like_delete(self, app, db_session, mock_redis):
        from app.likes.repositories import like_repository
        from tasks.like_tasks import async_like_to_do
        from tests.unit.factories import PostFactory, UserFactory
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            like_repository.create_post_like(user.id, post.id)
            result = async_like_to_do(user.id, "post", post.id, "delete", "test_pending")
            assert result["status"] == "success"
