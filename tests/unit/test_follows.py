# tests/unit/test_follows.py
import pytest
from app.follows.services import FollowService
from app.follows.models import Follow
from app.common.exceptions import ValidationError
from tests.unit.factories import UserFactory

class TestFollowService:
    """关注模块单元测试"""

    def test_follow_user_success(self, app, mock_redis,db_session):
        """测试关注用户成功"""
        with app.app_context():
            follower = UserFactory()  # 关注者
            followed = UserFactory()  # 被关注者
            follower_id=follower.id
            followed_id=followed.id
            # 执行关注
            result = FollowService.follow_user(follower_id, followed_id)
            assert result['message'] == '关注成功'
            assert result['follow']['follower_id'] == follower.id
            assert result['follow']['followed_id'] == followed.id

            # 验证关注记录
            follow = Follow.query.filter_by(follower_id=follower.id, followed_id=followed.id).first()
            assert follow is not None

    def test_follow_self(self, app,db_session, mock_redis):
        """测试关注自己（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            with pytest.raises(ValidationError) as excinfo:
                FollowService.follow_user(user.id, user.id)
            assert "不能关注自己" in str(excinfo.value)
