import pytest

from app.comments.models import Comment
from app.comments.services import CommentService
from app.common.exceptions import PermissionError, ResourceNotFoundError, ValidationError
from tests.unit.factories import CommentFactory, PostFactory, UserFactory


class TestCommentService:
    """评论模块单元测试"""

    def test_create_comment_success(self, app, db_session, mock_redis):
        with app.app_context():
            user = UserFactory(username="comment_user")
            post = PostFactory()
            user_id = user.id
            post_id = post.id
            data = {"post_id": post_id, "content": "这是测试评论"}

        result = CommentService.create_comment(user_id, data)

        assert result["message"] == "评论成功"
        comment_data = result["comment"]
        assert "id" in comment_data
        assert comment_data["user_id"] == user_id
        assert comment_data["content"] == "这是测试评论"
        assert comment_data["post_id"] == post_id

        with app.app_context():
            comment = db_session.get(Comment, comment_data["id"])
            assert comment is not None
            assert comment.content == "这是测试评论"

    def test_create_comment_nonexistent_post(self, app, db_session, mock_redis):
        with app.app_context():
            user = UserFactory(username="c_user2")
            user_id = user.id
            data = {"post_id": 999999, "content": "内容"}

        with pytest.raises(ResourceNotFoundError) as excinfo:
            CommentService.create_comment(user_id, data)
        assert "帖子(ID:999999)不存在" in str(excinfo.value)

    def test_delete_comment_by_owner(self, app, db_session, mock_redis):
        with app.app_context():
            user = UserFactory(username="owner_user")
            post = PostFactory()
            comment = CommentFactory(author=user, post=post)
            user_id = user.id
            comment_id = comment.id

        result = CommentService.delete_comment(comment_id, user_id)
        assert result["message"] == "评论删除成功"

        with app.app_context():
            c = db_session.get(Comment, comment_id)
            assert c.deleted_at is not None

    def test_delete_comment_not_owner(self, app, db_session, mock_redis):
        with app.app_context():
            owner = UserFactory(username="owner2")
            other = UserFactory(username="other_user")
            post = PostFactory()
            comment = CommentFactory(author=owner, post=post)
            other_id = other.id
            comment_id = comment.id

        with pytest.raises(PermissionError) as excinfo:
            CommentService.delete_comment(comment_id, other_id)
        assert "权限" in str(excinfo.value)

    def test_get_comments_for_post(self, app, db_session, mock_redis):
        with app.app_context():
            post = PostFactory()
            post_id = post.id
            CommentFactory.create_batch(3, post=post)

        result = CommentService.get_comments_by_post_id(post_id, page=1, per_page=10)

        items = result["items"]
        assert len(items) == 3
        for item in items:
            assert "id" in item
            assert "user_id" in item
            assert "post_id" in item

    def test_create_comment_empty_content(self, app, db_session, mock_redis):
        """测试空内容评论应抛出ValidationError"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            with pytest.raises(ValidationError) as excinfo:
                CommentService.create_comment(user.id, {"post_id": post.id, "content": ""})
            assert "不能为空" in str(excinfo.value)

    def test_create_comment_too_long(self, app, db_session, mock_redis):
        """测试超长内容应拒绝"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            with pytest.raises(ValidationError) as excinfo:
                CommentService.create_comment(user.id, {
                    "post_id": post.id,
                    "content": "a" * 501
                })
            assert "不能超过500" in str(excinfo.value)

    def test_get_hot_comments(self, app, db_session, mock_redis):
        """测试获取热评论列表"""
        with app.app_context():
            post = PostFactory()
            for i in range(3):
                comment = CommentFactory(post=post)
                from app.comments.cache import CommentCache
                CommentCache.update_hot_comment(post.id, comment.id, 10 - i)

            result = CommentService.get_hot_comments_by_post_id(post.id, page=1, per_page=10)
            assert "items" in result

    def test_comment_count_increment(self, app, db_session, mock_redis):
        """测试创建评论后帖子的 comment_count 增加"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            before = post.comment_count or 0

            CommentService.create_comment(user.id, {
                "post_id": post.id,
                "content": "测试评论"
            })

            from app.posts.repositories import post_repository
            updated = post_repository.get_by_id(post.id)
            assert updated.comment_count == before + 1

    def test_comment_count_decrement(self, app, db_session, mock_redis):
        """测试删除评论后帖子的 comment_count 减少"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            comment = CommentFactory(author=user, post=post)
            post.comment_count = 5
            db_session.commit()

            CommentService.delete_comment(comment.id, user.id)

            from app.posts.repositories import post_repository
            updated = post_repository.get_by_id(post.id)
            assert updated.comment_count == 4

    def test_update_comment_by_owner(self, app, db_session, mock_redis):
        """测试评论作者更新评论"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            comment = CommentFactory(author=user, post=post)

            result = CommentService.update_comment(
                comment.id, user.id, {"content": "更新后的内容"}
            )

            assert result["message"] == "评论更新成功"
            assert result["comment"]["content"] == "更新后的内容"

    def test_update_comment_not_owner(self, app, db_session, mock_redis):
        """测试非作者更新应抛出 PermissionError"""
        with app.app_context():
            owner = UserFactory()
            other = UserFactory()
            post = PostFactory()
            comment = CommentFactory(author=owner, post=post)

            with pytest.raises(PermissionError) as excinfo:
                CommentService.update_comment(comment.id, other.id, {"content": "hack"})
            assert "权限" in str(excinfo.value)

    def test_get_comment_by_id_cache_hit(self, app, db_session, mock_redis):
        """测试通过ID获取评论 - 缓存命中"""
        from app.comments.cache import CommentCache
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            comment = CommentFactory(author=user, post=post)
            comment_dict = {"id": comment.id, "content": "cached_content", "user_id": user.id, "post_id": post.id}
            CommentCache.set(comment.id, comment_dict)
            result = CommentService.get_comment_by_id(comment.id)
            assert result["content"] == "cached_content"

    def test_get_comment_by_id_cache_miss(self, app, db_session, mock_redis):
        """测试通过ID获取评论 - 缓存未命中，走DB"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            comment = CommentFactory(author=user, post=post)
            result = CommentService.get_comment_by_id(comment.id)
            assert result["id"] == comment.id
            assert result["content"] == comment.content

    def test_get_comment_by_id_not_found(self, app, db_session, mock_redis):
        """测试获取不存在的评论"""
        with app.app_context():
            with pytest.raises(ResourceNotFoundError) as excinfo:
                CommentService.get_comment_by_id(999999)
            assert "不存在" in str(excinfo.value)


class TestCommentCache:
    """评论缓存层单元测试"""
    def test_set_and_get_roundtrip(self, app, mock_redis):
        """写入后读取一致"""
        from app.comments.cache import CommentCache
        with app.app_context():
            data = {"id": 1, "content": "test"}
            CommentCache.set(1, data)
            assert CommentCache.get(1) == data

    def test_get_miss_returns_none(self, app, mock_redis):
        """未缓存返回None"""
        from app.comments.cache import CommentCache
        with app.app_context():
            assert CommentCache.get(9999999) is None

    def test_invalidate_remove_cache(self, app, mock_redis):
        """删除后get返回None"""
        from app.comments.cache import CommentCache
        with app.app_context():
            CommentCache.set(1, {"id": 1})
            CommentCache.invalidate(1)
            assert CommentCache.get(1) is None

    def test_comment_count_increment(self, app, mock_redis):
        """评论计数 +1"""
        from app.comments.cache import CommentCache
        with app.app_context():
            CommentCache.set_count(1, 0)
            CommentCache.increment_count(1)
            assert CommentCache.get_count(1) == 1

    def test_comment_count_decrement(self, app, mock_redis):
        """评论计数 -1"""
        from app.comments.cache import CommentCache
        with app.app_context():
            CommentCache.set_count(1, 0)
            CommentCache.increment_count(1)
            CommentCache.increment_count(1)
            CommentCache.decrement_count(1)
            assert CommentCache.get_count(1) == 1

    def test_hot_comments_cache(self, app, mock_redis):
        """热评ZSet缓存"""
        from app.comments.cache import CommentCache
        with app.app_context():
            CommentCache.update_hot_comment(1, 100, 50)
            CommentCache.update_hot_comment(1, 101, 30)
            ids, total = CommentCache.get_hot_comments(1, 1, 10)
            assert ids[0] == 100
