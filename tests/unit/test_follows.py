import pytest
from app.follows.services import FollowService
from app.follows.models import Follow
from app.common.exceptions import ValidationError, ConflictError, ResourceNotFoundError, DatabaseError
from tests.unit.factories import UserFactory

class TestFollowService:
    """关注模块单元测试"""

    def test_follow_user_success(self, app, mock_redis, db_session):
        """测试关注用户成功"""
        with app.app_context():
            follower = UserFactory()
            followed = UserFactory()
            result = FollowService.follow_user(follower.id, followed.id)
            assert result["message"] == "关注成功"
            assert result["follow"]["follower_id"] == follower.id
            assert result["follow"]["followed_id"] == followed.id

            follow = Follow.query.filter_by(
                follower_id=follower.id, followed_id=followed.id).first()
            assert follow is not None

    def test_follow_self(self, app, db_session, mock_redis):
        """测试关注自己（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            with pytest.raises(ValidationError) as excinfo:
                FollowService.follow_user(user.id, user.id)
            assert "不能关注自己" in str(excinfo.value)

    def test_unfollow_user_success(self, app, db_session, mock_redis):
        """测试取消关注成功"""
        with app.app_context():
            follower = UserFactory()
            followed = UserFactory()
            FollowService.follow_user(follower.id, followed.id)

            result = FollowService.unfollow_user(follower.id, followed.id)

            assert result["message"] == "取消成功"
            follow = Follow.query.filter_by(
                follower_id=follower.id,
                followed_id=followed.id).first()
            assert follow is None

    def test_follow_duplicate(self, app, db_session, mock_redis):
        """测试重复关注应该抛出ConflictError"""
        with app.app_context():
            follower = UserFactory()
            followed = UserFactory()
            FollowService.follow_user(follower.id, followed.id)
            with pytest.raises(ConflictError) as excinfo:
                FollowService.follow_user(follower.id, followed.id)
            assert "已关注" in str(excinfo.value)

    def test_get_following(self, app, db_session, mock_redis):
        """测试获取关注列表"""
        with app.app_context():
            user = UserFactory()
            for _ in range(3):
                followed = UserFactory()
                FollowService.follow_user(user.id, followed.id)
            result = FollowService.get_following(user.id, page=1, per_page=10)
            assert "follows" in result
            assert len(result["follows"]) == 3

    def test_get_followers(self, app, db_session, mock_redis):
        """测试获取粉丝列表"""
        with app.app_context():
            user = UserFactory()
            for _ in range(3):
                follower = UserFactory()
                FollowService.follow_user(follower.id, user.id)
            result = FollowService.get_followers(user.id, page=1, per_page=10)

            assert "follows" in result
            assert len(result["follows"]) == 3

    def test_get_mutual_follows(self, app, db_session, mock_redis):
        """测试获取互关列表"""
        with app.app_context():
            user_a = UserFactory()
            user_b = UserFactory()
            user_c = UserFactory()
            FollowService.follow_user(user_a.id, user_b.id)
            FollowService.follow_user(user_b.id, user_a.id)
            FollowService.follow_user(user_a.id, user_c.id)

            result = FollowService.get_mutual_follows(user_a.id)

            assert "mutual_users" in result
            assert len(result["mutual_users"]) == 1

    def test_follow_nonexistent_user(self, app, db_session, mock_redis):
        """测试关注不存在的用户"""
        with app.app_context():
            follower = UserFactory()
            with pytest.raises(ResourceNotFoundError) as excinfo:
                FollowService.follow_user(follower.id, 999999)
            assert "不存在" in str(excinfo.value)

    def test_is_following_check(self, app, db_session, mock_redis):
        """测试是否已关注（Redis + DB 双检查）"""
        with app.app_context():
            follower = UserFactory()
            followed = UserFactory()
            assert FollowService.is_following(follower.id, followed.id) is False
            FollowService.follow_user(follower.id, followed.id)
            assert FollowService.is_following(follower.id, followed.id) is True


class TestFollowCache:
    """关注缓存层单元测试"""
    def test_add_relation(self, app, mock_redis):
        """添加关注关系"""
        from app.follows.cache import FollowCache
        with app.app_context():
            FollowCache.add_relation(1, 2)
            assert FollowCache.is_following(1, 2) is True

    def test_remove_relation(self, app, mock_redis):
        """删除关注关系"""
        from app.follows.cache import FollowCache
        with app.app_context():
            FollowCache.add_relation(1, 2)
            FollowCache.remove_relation(1, 2)
            assert FollowCache.is_following(1, 2) is False

    def test_get_follower_ids(self, app, mock_redis):
        """获取粉丝ID列表"""
        from app.follows.cache import FollowCache
        with app.app_context():
            FollowCache.preload_followers(1, [10, 11, 12])
            ids = FollowCache.get_follower_ids(1)
            assert set(ids) == {"10", "11", "12"}

    def test_acquire_and_release_lock(self, app, mock_redis):
        """分布式锁"""
        from app.follows.cache import FollowCache
        with app.app_context():
            assert FollowCache.acquire_lock(1, 2) is True
            assert FollowCache.acquire_lock(1, 2) is False
            FollowCache.release_lock(1, 2)
            assert FollowCache.acquire_lock(1, 2) is True

    def test_invalidate(self, app, mock_redis):
        """清空用户缓存"""
        from app.follows.cache import FollowCache
        with app.app_context():
            FollowCache.add_relation(1, 2)
            FollowCache.invalidate(1)
            assert FollowCache.is_following(1, 2) is None
