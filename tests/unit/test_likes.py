import pytest

from app.common.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.likes.models import Like
from app.likes.services import LikeService
from tests.unit.factories import CommentFactory, PostFactory, UserFactory


class TestLikeService:
    """点赞模块单元测试"""

    def test_like_post_success(self, app, db_session, mock_redis):
        """测试点赞成功"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            user_id = user.id
            post_id = post.id

        with app.app_context():
            result = LikeService.create_like(user_id=user_id, post_id=post_id)

            assert 'id' in result
            assert result['user_id'] == user_id
            assert result['post_id'] == post_id
            assert 'created_at' in result

            like = Like.query.filter_by(user_id=user_id, post_id=post_id).first()
            assert like is not None

    def test_like_post_duplicate(self, app, db_session, mock_redis):
        """测试重复点赞（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            user_id = user.id
            post_id = post.id

            LikeService.create_like(user_id=user_id, post_id=post_id)

            with pytest.raises(ConflictError) as excinfo:
                LikeService.create_like(user_id=user_id, post_id=post_id)
            assert "您已点赞过了" in str(excinfo.value)

    def test_like_nonexistent_post(self, app, db_session, mock_redis):
        """测试点赞不存在的帖子（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            user_id = user.id
            non_existent_post_id = 999999

            with pytest.raises(ResourceNotFoundError) as excinfo:
                LikeService.create_like(user_id=user_id, post_id=non_existent_post_id)
            assert "帖子不存在" in str(excinfo.value)

    def test_like_post_without_user(self, app, db_session, mock_redis):
        """测试不存在的用户点赞（抛出异常）"""
        with app.app_context():
            non_existent_user_id = 999999
            post = PostFactory()
            post_id = post.id

            with pytest.raises(ResourceNotFoundError) as excinfo:
                LikeService.create_like(user_id=non_existent_user_id, post_id=post_id)
            assert "用户不存在" in str(excinfo.value)

    def test_like_post_without_post_and_comment(self, app, db_session, mock_redis):
        """测试既未提供post_id也未提供comment_id（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            user_id = user.id

            with pytest.raises(ValidationError) as excinfo:
                LikeService.create_like(user_id=user_id)
            assert "只能传入 post_id 或 comment_id" in str(excinfo.value)

    def test_like_comment_success(self, app, db_session, mock_redis):
        """测试评论点赞成功"""
        with app.app_context():
            user = UserFactory()
            comment = CommentFactory()
            user_id = user.id
            comment_id = comment.id
            result = LikeService.create_like(user_id=user_id, comment_id=comment_id)
            assert 'id' in result
            assert result['user_id'] == user_id
            assert result['comment_id'] == comment_id

    def test_unlike_post(self, app, db_session, mock_redis):
        """测试取消点赞帖子"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            LikeService.create_like(user_id=user.id, post_id=post.id)
            result = LikeService.delete_like(user_id=user.id, post_id=post.id)

            assert result is True
            like = Like.query.filter_by(
                user_id=user.id, post_id=post.id, is_delete=False).first()
            assert like is None

    def test_unlike_comment(self, app, db_session, mock_redis):
        """测试取消点赞评论"""
        with app.app_context():
            user = UserFactory()
            comment = CommentFactory()
            LikeService.create_like(user_id=user.id, comment_id=comment.id)
            result = LikeService.delete_like(user_id=user.id, comment_id=comment.id)
            assert result is None

    def test_like_count_redis_sync(self, app, db_session, mock_redis):
        """测试点赞后redis计数器+1"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            from app.likes.cache import LikeCache
            before = LikeCache.get_like_count(post.id, "post") or 0
            LikeService.create_like(user_id=user.id, post_id=post.id)
            after = LikeCache.get_like_count(post.id, "post")
            assert after == before + 1

    def test_unlike_nonexistent(self, app, db_session, mock_redis):
        """测试取消不存在的点赞记录"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            from app.common.exceptions import ResourceNotFoundError
            with pytest.raises(ResourceNotFoundError) as excinfo:
                LikeService.delete_like(user_id=user.id, post_id=post.id)
            assert "不存在" in str(excinfo.value)

    def test_delete_like_by_id_success(self, app, db_session, mock_redis):
        """测试通过like_id删除点赞"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            like = LikeService.create_like(user_id=user.id, post_id=post.id)
            like_id = like["id"]
            result = LikeService.delete_like_by_id(user.id, like_id, post_id=post.id)
            assert result is True

    def test_delete_like_by_id_not_owner(self, app, db_session, mock_redis):
        """测试非本人删除点赞应抛出PermissionError"""
        with app.app_context():
            owner = UserFactory()
            other = UserFactory()
            post = PostFactory()
            like = LikeService.create_like(user_id=owner.id, post_id=post.id)
            like_id = like["id"]

            from app.common.exceptions import PermissionError

            with pytest.raises(PermissionError) as excinfo:
                LikeService.delete_like_by_id(other.id, like_id, post_id=post.id)

            assert "无权限" in str(excinfo.value)

    def test_get_user_likes(self, app, db_session, mock_redis):
        """测试获取用户的点赞列表"""
        with app.app_context():
            user = UserFactory()
            for _ in range(3):
                post = PostFactory()
                LikeService.create_like(user_id=user.id, post_id=post.id)
            result = LikeService.get_user_likes(user.id, page=1, per_page=10)

            assert "items" in result
            assert len(result["items"]) == 3


class TestLikeCache:
    """点赞缓存层单元测试"""
    def test_add_like_and_check(self, app, mock_redis):
        """添加点赞后能查到"""
        from app.likes.cache import LikeCache
        with app.app_context():
            LikeCache.add_like(1, 100, "post")
            assert LikeCache.is_liked(1, 100, "post") is True

    def test_remove_like(self, app, mock_redis):
        """删除点赞后查不到"""
        from app.likes.cache import LikeCache
        with app.app_context():
            LikeCache.add_like(1, 100, "post")
            LikeCache.remove_like(1, 100, "post")
            assert LikeCache.is_liked(1, 100, "post") is False

    def test_like_count_sync(self, app, mock_redis):
        """点赞计数同步"""
        from app.likes.cache import LikeCache
        with app.app_context():
            LikeCache.add_like(1, 100, "post")
            count = LikeCache.get_like_count(100, "post")
            assert count == 1

    def test_like_count_decrement(self, app, mock_redis):
        """取消点赞计数 -1"""
        from app.likes.cache import LikeCache
        with app.app_context():
            LikeCache.add_like(1, 100, "post")
            LikeCache.remove_like(1, 100, "post")
            count = LikeCache.get_like_count(100, "post")
            assert count == 0

    def test_acquire_and_release_lock(self, app, mock_redis):
        """分布式锁获取与释放"""
        from app.likes.cache import LikeCache
        with app.app_context():
            assert LikeCache.acquire_lock(1, 100, "post") is True
            assert LikeCache.acquire_lock(1, 100, "post") is False
            LikeCache.release_lock(1, 100, "post")
            assert LikeCache.acquire_lock(1, 100, "post") is True

    def test_preload_user_likes(self, app, mock_redis):
        """批量预热用户点赞状态"""
        from app.likes.cache import LikeCache
        with app.app_context():
            LikeCache.preload_user_likes(1, [100, 101, 102])
            assert LikeCache.is_liked(1, 100, "post") is True
            assert LikeCache.is_liked(1, 101, "post") is True
