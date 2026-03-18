from app.comments.models import Comment
import pytest
from app.comments.services import CommentService
from app.comments.models import Comment
from app.posts.models import Post
from app.common.exceptions import ResourceNotFoundError, PermissionError
from tests.unit.factories import UserFactory, PostFactory, CommentFactory

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
            assert c.is_deleted is True

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
