from app.posts.models import Post
import pytest
from app.posts.services import PostService
from app.likes.services import LikeService
from app.posts.models import Post
from app.common.exceptions import ValidationError, ResourceNotFoundError, AuthenticationError
from tests.unit.factories import UserFactory, PostFactory

class TestPostService:
    """帖子模块单元测试"""

    def test_create_post_success(self, app, db_session, mock_redis):
        """测试创建帖子成功"""
        with app.app_context():
            user = UserFactory()
            user_id = user.id
            content = "测试创建帖子的有效内容"

        result = PostService.create_post(user_id, content)

        # 验证返回格式
        assert result["message"] == "帖子创建成功"
        post_data = result["post"]
        assert post_data["content"] == content
        assert "id" in post_data
        assert post_data["user_id"] == user_id
        assert "author" in post_data  # 可能包含作者信息
        assert "like_count" in post_data

        # 验证数据库
        with app.app_context():
            post = db_session.get(Post, post_data["id"])
            assert post is not None
            assert post.user_id == user_id
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
        """测试查询用户帖子列表"""
        with app.app_context():
            user = UserFactory()
            user_id = user.id
            # 创建3个帖子（使用 user 关系）
            PostFactory.create_batch(3, author=user)

            result = PostService.get_posts(page=1, per_page=10, user_id=user_id, current_user_id=user_id)

        # 服务层返回结构：{'posts': [...], 'pagination': {...}}
        assert "posts" in result
        posts = result["posts"]
        assert len(posts) == 3
        for post in posts:
            assert post["user_id"] == user_id
            assert "has_liked" in post
            # 因为当前用户就是作者，且未点赞，has_liked 应为 False
            assert post["has_liked"] is False

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
        assert "has_liked" in post_data
        assert post_data["has_liked"] is False

    def test_update_post_success(self, app, db_session, mock_redis):
        """测试更新帖子成功"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)
            post_id = post.id
            user_id = user.id
            new_content = "更新后的内容"

            result = PostService.update_post(post_id, user_id, content=new_content)

        assert result["message"] == "帖子更新成功"
        post_data = result["post"]
        assert post_data["content"] == new_content

        with app.app_context():
            updated = db_session.get(Post, post_id)
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
        """测试删除帖子成功"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)
            post_id = post.id
            user_id = user.id

            result = PostService.delete_post(post_id, user_id)

        assert result["message"] == "帖子删除成功"

        with app.app_context():
            deleted = db_session.get(Post, post_id)
            assert deleted.is_deleted is True

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

    def test_like_post(self, app, db_session, mock_redis):
        """测试点赞帖子"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)
            post_id = post.id
            user_id = user.id

            result = LikeService.create_like(user_id=user_id, post_id=post_id)

        # LikeService.create_like 返回点赞序列化数据
        assert result["user_id"] == user_id
        assert result["post_id"] == post_id

        with app.app_context():
            from app.likes.models import Like
            like = Like.query.filter_by(user_id=user_id, post_id=post_id).first()
            assert like is not None
            updated_post = db_session.get(Post, post_id)
            assert updated_post.like_count == 1

    def test_unlike_post(self, app, db_session, mock_redis):
        """测试取消点赞"""
        with app.app_context():
            user = UserFactory()
            post = PostFactory(author=user)
            post_id = post.id
            user_id = user.id
            # 先点赞
            LikeService.create_like(user_id=user_id, post_id=post_id)

            result = LikeService.delete_like(user_id=user_id, post_id=post_id)

        # LikeService.delete_like 返回 True
        assert result is True

        with app.app_context():
            from app.likes.models import Like
            like = Like.query.filter_by(user_id=user_id, post_id=post_id, is_deleted=False).first()
            assert like is None
            updated_post = db_session.get(Post, post_id)
            assert updated_post.like_count == 0
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
