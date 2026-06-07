import factory
from factory.alchemy import SQLAlchemyModelFactory
from datetime import datetime
from app.common.database import utcnow
from app.users.models import User
from app.posts.models import Post
from app.comments.models import Comment  # 先导入 Comment
from app.likes.models import Like
from app.follows.models import Follow
from app.notifications.models import Notification  # 修正导入
from utils.snowflake_util import Snowflake

class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"

# 雪花ID生成器实例
snowflake = Snowflake(machine_id=1, service_id=1)

# ---------------------- 用户数据工厂 ----------------------
class UserFactory(BaseFactory):
    class Meta:
        model = User
    id = factory.LazyAttribute(lambda _: snowflake.get_id())
    username = factory.Sequence(lambda n: f"test_user_{n}")
    password_hash = "test_hash_123456"
    email = factory.Sequence(lambda n: f"test_user_{n}@example.com")
    created_at = factory.LazyFunction(utcnow)

# ---------------------- 帖子数据工厂 ----------------------
class PostFactory(BaseFactory):
    class Meta:
        model = Post
    id = factory.LazyAttribute(lambda _: snowflake.get_id())
    author = factory.SubFactory(UserFactory)
    content = factory.Sequence(lambda n: f"测试帖子内容{n}，包含各种测试场景")
    like_count = 0
    deleted_at = None
    created_at = factory.LazyFunction(utcnow)
    updated_at = factory.LazyFunction(utcnow)

# ---------------------- 评论数据工厂 ----------------------
class CommentFactory(BaseFactory):
    class Meta:
        model = Comment
    id = factory.LazyAttribute(lambda _: snowflake.get_id())
    author = factory.SubFactory(UserFactory)  # 修正为author
    post = factory.SubFactory(PostFactory)
    content = factory.Sequence(lambda n: f"测试评论内容{n}")
    deleted_at = None
    like_count = 0
    created_at = factory.LazyFunction(utcnow)
    updated_at = factory.LazyFunction(utcnow)

# ---------------------- 点赞数据工厂 ----------------------
class LikeFactory(BaseFactory):
    class Meta:
        model = Like
    id = factory.LazyAttribute(lambda _: snowflake.get_id())
    user = factory.SubFactory(UserFactory)
    post = factory.SubFactory(PostFactory)
    comment = factory.SubFactory(CommentFactory)
    created_at = factory.LazyFunction(utcnow)

# ---------------------- 关注数据工厂 ----------------------
class FollowFactory(BaseFactory):
    class Meta:
        model = Follow
    id = factory.LazyAttribute(lambda _: snowflake.get_id())
    follower = factory.SubFactory(UserFactory)
    followed = factory.SubFactory(UserFactory)
    created_at = factory.LazyFunction(utcnow)

# ---------------------- 通知数据工厂 ----------------------
class NotificationFactory(BaseFactory):
    class Meta:
        model = Notification
    id = factory.LazyAttribute(lambda _: snowflake.get_id())
    user = factory.SubFactory(UserFactory)
    user_id = factory.SelfAttribute('user.id')
    actor = factory.SubFactory(UserFactory)
    type = factory.Sequence(lambda n: f"notification_type_{n}")
    resource_id = None
    resource_type = None
    content = factory.Sequence(lambda n: f"通知内容 {n}")
    is_read = False
    created_at = factory.LazyFunction(utcnow)
