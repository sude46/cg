# tests/integration/test_flows.py
import pytest
from app.auth.services import AuthService
from app.posts.services import PostService, LikeService
from app.comments.services import CommentService
from app.posts.models import Post, Like
from app.comments.models import Comment

class TestCoreBusinessFlow:
    """核心业务流集成测试"""

    def test_full_business_flow(self, app, mock_redis, mock_mq, mock_third_party_service):
        """测试完整业务流：注册→登录→发帖→评论→点赞→删除帖子"""
        with app.app_context():
            # ---------------------- 步骤1：用户注册 ----------------------
            username = "integration_test_user"
            password = "12345678"
            register_result = AuthService.create_user(username, password)
            user_id = register_result["id"]
            assert user_id is not None

            # ---------------------- 步骤2：用户登录 ----------------------
            login_result = AuthService.login(username, password)
            token = login_result["token"]
            assert token is not None
            assert login_result["user_id"] == user_id

            # ---------------------- 步骤3：创建帖子 ----------------------
            post_content = "集成测试：创建测试帖子"
            post_result = PostService.create_post(user_id, post_content)
            post_id = post_result["id"]
            assert post_id is not None

            # 验证帖子已创建
            post = Post.query.filter_by(id=post_id).first()
            assert post is not None
            assert post.content == post_content

            # ---------------------- 步骤4：评论帖子 ----------------------
            comment_content = "集成测试：测试评论"
            comment_result = CommentService.create_comment(user_id, post_id, comment_content)
            comment_id = comment_result["id"]
            assert comment_id is not None

            # 验证评论已创建
            comment = Comment.query.filter_by(id=comment_id).first()
            assert comment is not None
            assert comment.content == comment_content

            # ---------------------- 步骤5：点赞帖子 ----------------------
            request_id = "integration_test_request_id"
            like_result = LikeService.like_post(post_id, user_id, request_id)
            assert like_result is True

            # 验证点赞已创建+帖子点赞数更新
            like = Like.query.filter_by(user_id=user_id, post_id=post_id).first()
            assert like is not None
            post = Post.query.filter_by(id=post_id).first()
            assert post.like_count == 1

            # ---------------------- 步骤6：删除帖子 ----------------------
            delete_result = PostService.delete_post(post_id, user_id)
            assert delete_result is True

            # 验证帖子已软删除
            post = Post.query.filter_by(id=post_id).first()
            assert post.is_deleted is True
            # 验证评论/点赞是否级联删除（根据业务逻辑调整）
            comment = Comment.query.filter_by(id=comment_id).first()
            assert comment.is_deleted is True