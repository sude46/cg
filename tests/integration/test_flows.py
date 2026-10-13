import pytest

from app.comments.models import Comment
from app.comments.services import CommentService
from app.feeds.services import FeedService
from app.follows.services import FollowService
from app.likes.models import Like
from app.likes.services import LikeService
from app.posts.models import Post
from app.posts.services import PostService
from app.users.services import AuthService


class TestCoreBusinessFlow:
    """核心业务流集成测试"""
    def test_full_business_flow(self, app, db_session, mock_redis):
        """测试完整业务流:注册->登录->发帖->评论->点赞->删除帖子"""
        with app.app_context():
            username = "flow_user"
            email = "flow@test.com"
            password = "Pass@w0rd!"
            register_result = AuthService.register_user(username, email, password)
            user_id = register_result["user"]["id"]
            assert user_id is not None

            login_result = AuthService.authenticate_user(username, password)
            assert "access_token" in login_result
            assert login_result["user"]["id"] == user_id

            post_content = "集成测试帖子"
            post = PostService.create_post(user_id, post_content)

            post_id = post.id
            assert post_id is not None
            assert post.content == post_content

            comment_data = {"post_id": post_id, "content": "集成测试评论"}
            comment_result = CommentService.create_comment(user_id, comment_data)
            assert comment_result["message"] == "评论成功"
            comment_id = comment_result["comment"]["id"]

            comment = db_session.get(Comment, comment_id)
            assert comment is not None
            assert comment.content == "集成测试评论"

            like_result = LikeService.create_like(user_id=user_id, post_id=post_id)
            assert like_result["post_id"] == post_id

            like = Like.query.filter_by(user_id=user_id, post_id=post_id).first()
            assert like is not None

            PostService.delete_post(post_id, user_id)

            deleted_post = db_session.get(Post, post_id)
            assert deleted_post.deleted_at is not None


class TestFollowFeedFlow:
    """关注+Feed流集成测试"""
    def test_follow_and_feed_flow(self, app, db_session, mock_redis):
        """关注用户->发帖->查看Feed时间线"""
        with app.app_context():
            follower = AuthService.register_user(
                "follower", "follower@test.com", "Pass@w0rd!"
            )["user"]
            author = AuthService.register_user(
                "author", "author@test.com", "Pass@w0rd!"
            )["user"]

            FollowService.follow_user(follower["id"], author["id"])

            post = PostService.create_post(author["id"], "Feed测试帖子")

            FeedService.publish_post(post.id, author["id"], post.created_at)

            timeline = FeedService.get_timeline(follower["id"], limit=10)

            assert any(it["id"] == post.id for it in timeline["items"])


class TestNotificationFlow:
    """通知触发集成测试"""
    def test_like_notification_flow(self, app, db_session, mock_redis):
        """点赞帖子 → 触发通知创建"""
        with app.app_context():
            author = AuthService.register_user(
                "notif_author", "na@test.com", "Pass@w0rd!"
            )["user"]
            liker = AuthService.register_user(
                "notif_liker", "nl@test.com", "Pass@w0rd!"
            )["user"]
            post = PostService.create_post(author["id"], "通知测试帖子")
            LikeService.create_like(user_id=liker["id"], post_id=post.id)

            from app.notifications.models import Notification
            Notification.query.filter_by(
                user_id=author["id"], type="like"
            ).first()

    def test_comment_notification_flow(self, app, db_session, mock_redis):
        """评论帖子->触发通知创建"""
        with app.app_context():
            author = AuthService.register_user(
                "comm_author", "ca@test.com", "Pass@w0rd!"
            )["user"]
            commenter = AuthService.register_user(
                "commenter", "cc@test.com", "Pass@w0rd!"
            )["user"]
            post = PostService.create_post(author["id"], "评论通知测试")
            CommentService.create_comment(commenter["id"], {
                "post_id": post.id,
                "content": "测试评论"
            })


class TestCacheConsistencyFlow:
    """缓存一致性集成测试"""
    def test_cache_consistency_flow(self, app, db_session, mock_redis):
        """写入->缓存->读取->更新->缓存失效->读取"""
        with app.app_context():
            user = AuthService.register_user(
                "cache_user", "cache@test.com", "Pass@w0rd!")["user"]
            post = PostService.create_post(user["id"], "缓存一致性测试")
            post_id = post.id

            from app.posts.cache import PostCache
            cached1 = PostCache.get(post_id)
            assert cached1 is not None
            assert cached1["content"] == "缓存一致性测试"

            PostService.update_post(post_id, user["id"], content="更新后的内容")

            cached2 = PostCache.get(post_id)
            assert cached2 is None

            assert PostCache.is_recently_modified(post_id) is True

            result = PostService.get_post(post_id)
            assert result["post"]["content"] == "更新后的内容"


class TestJWTAuthFlow:
    """JWT认证流程集成测试"""
    def test_jwt_auth_flow(self, app, db_session, mock_redis):
        """登录 → 获取令牌 → 访问受保护接口 → 登出 → 令牌失效"""
        with app.app_context():
            user = AuthService.register_user(
                "jwt_user", "jwt@test.com", "Pass@w0rd!"
            )["user"]
            login = AuthService.authenticate_user("jwt_user", "Pass@w0rd!")
            access_token = login["access_token"]
            login["refresh_token"]
            assert access_token is not None

            refresh = AuthService.refresh_token(user["id"])
            assert "access_token" in refresh

            current = AuthService.get_current_user(user["id"])
            assert current["user"]["username"] == "jwt_user"


class TestConcurrentLikeFlow:
    """并发点赞幂等性集成测试"""
    def test_concurrent_like_flow(self, app, db_session, mock_redis):
        """并发点赞的幂等性验证"""
        with app.app_context():
            user = AuthService.register_user(
                "concurrent_user", "concurrent@test.com", "Pass@w0rd!"
            )["user"]
            post = PostService.create_post(user["id"], "并发测试")
            result1 = LikeService.create_like(user_id=user["id"], post_id=post.id)
            assert result1["post_id"] == post.id

            from app.common.exceptions import ConflictError
            with pytest.raises(ConflictError):
                LikeService.create_like(user_id=user["id"], post_id=post.id)

            likes = Like.query.filter_by(user_id=user["id"], post_id=post.id).all()
            assert len(likes) == 1
