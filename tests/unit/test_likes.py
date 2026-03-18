import pytest
from app.likes.services import LikeService
from app.likes.models import Like
from app.common.exceptions import DatabaseError, ResourceNotFoundError, ValidationError,ConflictError
from tests.unit.factories import UserFactory, PostFactory, CommentFactory

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
            # 执行点赞
            result = LikeService.create_like(user_id=user_id, post_id=post_id)

            # 断言返回的是包含点赞信息的字典
            assert 'id' in result
            assert result['user_id'] == user_id
            assert result['post_id'] == post_id
            assert 'created_at' in result

            # 验证点赞记录已创建
            like = Like.query.filter_by(user_id=user_id, post_id=post_id).first()
            assert like is not None

    def test_like_post_duplicate(self, app, db_session, mock_redis):
        """测试重复点赞（抛出异常）"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory()
            user_id = user.id
            post_id = post.id

            # 先点赞一次
            LikeService.create_like(user_id=user_id, post_id=post_id)

            # 重复点赞应抛出 ConflictError
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
            comment = CommentFactory()  # 需要导入 CommentFactory
            user_id = user.id
            comment_id = comment.id
            result = LikeService.create_like(user_id=user_id, comment_id=comment_id)
            assert 'id' in result
            assert result['user_id'] == user_id
            assert result['comment_id'] == comment_id

