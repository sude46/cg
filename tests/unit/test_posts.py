import pytest

from app.common.exceptions import AuthenticationError, ValidationError
from app.posts.models import Post
from app.posts.services import PostService
from tests.unit.factories import PostFactory, UserFactory


class TestPostService:
    """帖子模块单元测试"""

    def test_create_post_success(self, app, db_session, mock_redis):
        """测试创建帖子成功（service 返回 Post ORM）"""
        with app.app_context():
            user = UserFactory()
            content = "测试创建帖子的有效内容"

            result = PostService.create_post(user.id, content)

            assert isinstance(result, Post)
            assert result.content == content
            assert result.user_id == user.id
            assert result.id is not None

            post = db_session.get(Post, result.id)
            assert post is not None
            assert post.content == content

    def test_create_post_empty_content(self, app, db_session, mock_redis):
        """测试创建空内容帖子（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            user_id = user.id

        with pytest.raises(ValidationError) as excinfo:
            PostService.create_post(user_id, "")
        assert "帖子内容不能为空" in str(excinfo.value)

    def test_create_post_too_long_content(self, app, db_session, mock_redis):
        """测试创建超长内容帖子（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            user_id = user.id
            long_content = "a" * 1001

        with pytest.raises(ValidationError) as excinfo:
            PostService.create_post(user_id, long_content)
        assert "不能超过1000个字符" in str(excinfo.value)

    def test_get_user_posts(self, app, db_session, mock_redis):
        """测试查询用户帖子列表（service 返回 ORM items + liked_post_ids）"""
        with app.app_context():
            user = UserFactory()
            PostFactory.create_batch(3, author=user)

            result = PostService.get_posts(page=1, per_page=10, user_id=user.id, current_user_id=user.id)

            assert "items" in result
            posts = result["items"]
            assert len(posts) == 3
            for post in posts:
                assert post.user_id == user.id
            assert "liked_post_ids" in result

    def test_get_post_detail(self, app, db_session, mock_redis):
        """测试获取帖子详情"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)
            post_id = post.id

            result = PostService.get_post(post_id, current_user_id=user.id)

        assert "post" in result
        post_data = result["post"]
        assert post_data["id"] == post_id
        assert post_data["user_id"] == user.id
        assert result["has_liked"] is False

    def test_update_post_success(self, app, db_session, mock_redis):
        """测试更新帖子成功（service 返回 Post ORM）"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)
            new_content = "更新后的内容"

            result = PostService.update_post(post.id, user.id, content=new_content)

            assert isinstance(result, Post)
            assert result.content == new_content

            updated = db_session.get(Post, post.id)
            assert updated.content == new_content

    def test_update_post_not_owner(self, app, db_session, mock_redis):
        """测试非作者更新帖子（抛出异常）"""
        with app.app_context():
            owner = UserFactory()
            other = UserFactory()
            post = PostFactory(author=owner)
            post_id = post.id
            other_id = other.id

        with pytest.raises(AuthenticationError) as excinfo:
            PostService.update_post(post_id, other_id, content="新内容")
        assert "无权修改" in str(excinfo.value)

    def test_delete_post_success(self, app, db_session, mock_redis):
        """测试删除帖子成功（service 返回 None，软删除生效）"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)

            result = PostService.delete_post(post.id, user.id)

            assert result is None
            deleted = db_session.get(Post, post.id)
            assert deleted.deleted_at is not None

    def test_delete_post_not_owner(self, app, db_session, mock_redis):
        """测试非作者删除帖子（抛出异常）"""
        with app.app_context():
            owner = UserFactory()
            other = UserFactory()
            post = PostFactory(author=owner)
            post_id = post.id
            other_id = other.id

        with pytest.raises(AuthenticationError) as excinfo:
            PostService.delete_post(post_id, other_id)
        assert "无权删除" in str(excinfo.value)

    def test_update_post_no_updates(self, app, db_session, mock_redis):
        """测试未提供任何更新内容（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)
            post_id = post.id
            user_id = user.id

        with pytest.raises(ValidationError) as excinfo:
            PostService.update_post(post_id, user_id)  # 不提供 content 和 image_url
        assert "至少提供一个更新内容" in str(excinfo.value)
    def test_search_posts(self, app, db_session, mock_redis, monkeypatch):
        """ES 故障时降级到 DB LIKE 搜索；0 结果不回退"""
        from services.search.document import SearchBackendError
        with app.app_context():
            user = UserFactory()
            PostFactory(author=user, content="Python 教程")
            PostFactory(author=user, content="Flask 入门")

            def _boom(**kwargs):
                raise SearchBackendError("es down")

            monkeypatch.setattr(
                "services.search.services.PostSearchRepository.search", _boom
            )

            result = PostService.search_posts("Python", page=1, per_page=10)

            assert "items" in result
            assert result.get("is_es_search") is False

    def test_get_hot_posts(self, app, db_session, mock_redis):
        """测试获取热帖列表"""
        with app.app_context():
            user = UserFactory()
            for i in range(3):
                post = PostFactory(author=user)
                from app.posts.cache import PostCache
                PostCache.update_hot_posts([{'post_id': post.id, 'score': 100 - i}], period="daily")

            result = PostService.get_hot_posts(page=1, per_page=10, period="daily")

            assert "items" in result
            assert len(result["items"]) <= 10

    def test_delete_post_cascade_events(self, app, db_session, mock_redis, monkeypatch):
        """测试删除帖子时事件发布"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)

            published = []
            import app.posts.services as post_services
            monkeypatch.setattr(
                post_services.event_bus, "publish",
                lambda *a, **k: published.append(a)
            )

            PostService.delete_post(post.id, user.id)

            assert published

    def test_concurrent_update_stale_data(self, app, db_session, mock_redis, monkeypatch):
        """测试并发更新检测 StaleDataError"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)

            # mock 让 post_repository 抛出 StaleDataError
            from sqlalchemy.orm.exc import StaleDataError
            def raise_stale(*args, **kwargs):
                raise StaleDataError()

            monkeypatch.setattr(
                'app.posts.repositories.post_repository.get_by_id',
                raise_stale
            )

            from app.common.exceptions import ConflictError
            with pytest.raises(ConflictError) as excinfo:
                PostService.update_post(post.id, user.id, content="新内容")
            assert "已被其他用户修改" in str(excinfo.value)



class TestPostCache:
    """帖子缓存层单元测试"""

    def test_set_and_get_roundtrip(self, app, mock_redis):
        """测试缓存写入后能正确读出"""
        from app.posts.cache import PostCache as cache

        data = {'id': 999, 'content': 'hello'}
        cache.set(999, data)
        cached = cache.get(999)
        assert cached == data

    def test_get_miss_returns_none(self, app, mock_redis):
        """测试未缓存的 key 返回 None"""
        from app.posts.cache import PostCache as cache

        result = cache.get('nonexistent')
        assert result is None

    def test_invalidate_removes_cache(self, app, mock_redis):
        """测试删除缓存后 get 返回 None"""
        from app.posts.cache import PostCache as cache

        cache.set(1, {'id': 1})
        cache.invalidate(1)
        assert cache.get(1) is None

    def test_recently_modified_mark_and_check(self, app, mock_redis):
        """测试强一致标记设置与检查"""
        from app.posts.cache import PostCache as cache

        cache.mark_recently_modified(1, ttl=5)
        assert cache.is_recently_modified(1) is True

    def test_recently_modified_survives_invalidation(self, app, mock_redis):
        """invalidate 只删详情缓存，不清理强一致标记（由 TTL 自然过期，
        否则会提前结束延迟双删的强一致窗口）"""
        from app.posts.cache import PostCache as cache

        cache.mark_recently_modified(1, ttl=5)
        assert cache.is_recently_modified(1) is True
        cache.invalidate(1)
        assert cache.get(1) is None
        assert cache.is_recently_modified(1) is True

    def test_null_penetration_protection(self, app, mock_redis):
        """测试 None 值缓存空标记，重复 get 仍返回 None"""
        from app.posts.cache import PostCache as cache

        cache.set(1, None)
        result = cache.get(1)
        assert result is None

    def test_preload_profiles_warms_cache(self, app, mock_redis):
        """测试批量预热"""
        from app.posts.cache import PostCache as cache

        posts = [{'id': i, 'content': f'post{i}'} for i in range(3)]
        for p in posts:
            cache.set(p['id'], p)
        for p in posts:
            assert cache.get(p['id']) == p


