import pytest

from app.common.exceptions import ResourceNotFoundError, ValidationError
from app.notifications.models import Notification
from app.notifications.services import NotificationService
from tests.unit.factories import NotificationFactory, UserFactory


class TestNotificationService:
    """通知模块单元测试"""

    def test_create_notification_success(self, app, db_session, mock_redis):
        """测试创建通知成功"""
        with app.app_context():
            user = UserFactory()
            actor = UserFactory()
            data = {
                "user_id": user.id,
                "actor_id": actor.id,
                "type": "comment",
                "resource_id": 1,
                "resource_type": "post",
                "content": "有人评论了你的帖子",
            }

            result = NotificationService.create_notification(data)

            assert "id" in result
            assert result["user_id"] == user.id
            assert result["actor_id"] == actor.id
            assert result["type"] == "comment"
            assert result["content"] == "有人评论了你的帖子"
            assert result["is_read"] is False

            notif = db_session.get(Notification, result["id"])
            assert notif is not None
            assert notif.user_id == user.id

    def test_create_notification_invalid_user(self, app, db_session, mock_redis):
        """测试创建通知时目标用户不存在"""
        with app.app_context():
            actor = UserFactory()
            data = {
                "user_id": 999999,
                "actor_id": actor.id,
                "type": "comment",
                "content": "测试",
            }

            with pytest.raises(ResourceNotFoundError) as excinfo:
                NotificationService.create_notification(data)
            assert "用户(ID:999999)不存在" in str(excinfo.value)

    def test_create_notification_invalid_actor(self, app, db_session, mock_redis):
        """测试创建通知时触发用户不存在"""
        with app.app_context():
            user = UserFactory()
            data = {
                "user_id": user.id,
                "actor_id": 999999,
                "type": "comment",
                "content": "测试",
            }

            with pytest.raises(ResourceNotFoundError) as excinfo:
                NotificationService.create_notification(data)
            assert "触发用户(ID:999999)不存在" in str(excinfo.value)

    def test_create_notification_missing_user_id(self, app, db_session, mock_redis):
        """测试创建通知时缺少 user_id"""
        with app.app_context():
            data = {
                "actor_id": 1,
                "type": "comment",
                "content": "测试",
            }

            with pytest.raises(ValidationError) as excinfo:
                NotificationService.create_notification(data)
            assert "缺少 recipient user_id" in str(excinfo.value)

    def test_get_notification_by_id_success(self, app, db_session, mock_redis):
        """测试用户获取自己的通知成功"""
        with app.app_context():
            user = UserFactory()
            notif = NotificationFactory(user=user)
            notif_id = notif.id
            result = NotificationService.get_notification_by_id(notif_id, user.id)

            assert result["id"] == notif_id
            assert result["user_id"] == user.id

    def test_get_notification_by_id_not_owned(self, app, db_session, mock_redis):
        """测试用户获取不属于自己的通知"""
        with app.app_context():
            owner = UserFactory()
            other = UserFactory()
            notif = NotificationFactory(user=owner)
            notif_id = notif.id

            with pytest.raises(ResourceNotFoundError) as excinfo:
                NotificationService.get_notification_by_id(notif_id, other.id)
            assert "不存在或无权访问" in str(excinfo.value)

    def test_get_notification_by_id_not_found(self, app, db_session, mock_redis):
        """测试获取不存在的通知"""
        with app.app_context():
            user = UserFactory()

            with pytest.raises(ResourceNotFoundError) as excinfo:
                NotificationService.get_notification_by_id(999999, user.id)
            assert "不存在或无权访问" in str(excinfo.value)

    def test_get_user_notifications(self, app, db_session, mock_redis):
        """测试获取用户通知列表"""
        with app.app_context():
            user = UserFactory()
            NotificationFactory.create_batch(5, user=user)
            db_session.commit()
            count = Notification.query.filter_by(user_id=user.id).count()
            assert count == 5

            result = NotificationService.get_user_notifications(user.id, page=1, per_page=10)

            assert len(result["items"]) == 5
            assert result["pagination"]["total"] == 5

    def test_get_user_notifications_unread_only(self, app, db_session, mock_redis):
        """测试仅获取未读通知"""
        with app.app_context():
            user = UserFactory()
            NotificationFactory.create_batch(3, user=user, is_read=False)
            NotificationFactory.create_batch(2, user=user, is_read=True)
            db_session.commit()
            count = Notification.query.filter_by(user_id=user.id).count()
            assert count == 5

            result = NotificationService.get_user_notifications(user.id, unread_only=True)

            assert len(result["items"]) == 3
            for item in result["items"]:
                assert item["is_read"] is False

    def test_mark_as_read_success(self, app, db_session, mock_redis):
        """测试标记通知为已读成功"""
        with app.app_context():
            user = UserFactory()
            notif = NotificationFactory(user=user, is_read=False)
            notif_id = notif.id

            result = NotificationService.mark_as_read(notif_id, user.id)

            assert result["is_read"] is True

            updated = db_session.get(Notification, notif_id)
            assert updated.is_read is True

    def test_mark_as_read_not_owned(self, app, db_session, mock_redis):
        """测试标记不属于自己的通知为已读"""
        with app.app_context():
            owner = UserFactory()
            other = UserFactory()
            notif = NotificationFactory(user=owner)
            notif_id = notif.id

            with pytest.raises(ResourceNotFoundError) as excinfo:
                NotificationService.mark_as_read(notif_id, other.id)
            assert "不存在或无权访问" in str(excinfo.value)

    def test_mark_all_as_read(self, app, db_session, mock_redis):
        """测试标记用户所有通知为已读"""
        with app.app_context():
            user = UserFactory()
            NotificationFactory.create_batch(5, user=user, is_read=False)

            NotificationService.mark_all_as_read(user.id)

            unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
            assert unread_count == 0

    def test_delete_notification_success(self, app, db_session, mock_redis):
        """测试删除通知成功"""
        with app.app_context():
            user = UserFactory()
            notif = NotificationFactory(user=user)
            notif_id = notif.id

            NotificationService.delete_notification(notif_id, user.id)

            deleted = db_session.get(Notification, notif_id)
            assert deleted is None or deleted.deleted_at is not None

    def test_delete_notification_not_owned(self, app, db_session, mock_redis):
        """测试删除不属于自己的通知"""
        with app.app_context():
            owner = UserFactory()
            other = UserFactory()
            notif = NotificationFactory(user=owner)
            notif_id = notif.id

            with pytest.raises(ResourceNotFoundError) as excinfo:
                NotificationService.delete_notification(notif_id, other.id)
            assert "不存在或无权访问" in str(excinfo.value)

class TestNotificationCache:
    """通知缓存层单元测试"""
    def test_unread_count_increment(self, app, mock_redis):
        """未读计数 +1"""
        from app.notifications.cache import NotificationCache
        with app.app_context():
            NotificationCache.set_unread_count(1, 0)
            NotificationCache.increment_unread(1)
            assert NotificationCache.get_unread_count(1) == 1

    def test_unread_count_decrement(self, app, mock_redis):
        """未读计数 -1"""
        from app.notifications.cache import NotificationCache
        with app.app_context():
            NotificationCache.set_unread_count(1, 0)
            NotificationCache.increment_unread(1)
            NotificationCache.increment_unread(1)
            NotificationCache.decrement_unread(1)
            assert NotificationCache.get_unread_count(1) == 1

    def test_mark_all_as_read(self,app,mock_redis):
        """全部标记已读"""
        from app.notifications.cache import NotificationCache
        with app.app_context():
            NotificationCache.set_unread_count(1, 0)
            NotificationCache.increment_unread(1)
            NotificationCache.clear_unread(1)
            assert NotificationCache.get_unread_count(1)==0
    def test_recently_modified(self,app,mock_redis):
        """强一致标记"""
        from app.notifications.cache import NotificationCache
        with app.app_context():
            NotificationCache.mark_recently_modified(1,ttl=5)
            assert NotificationCache.is_recently_modified(1) is True

    def test_double_invalidate(self,app,mock_redis):
        """延迟双删"""
        from app.notifications.cache import NotificationCache
        with app.app_context():
            NotificationCache.set_unread_count(1,5)
            NotificationCache.double_invalidate_unread(1)
            #验证第一次删除
            assert NotificationCache.get_unread_count(1) is None

    def test_empty_cache_protection(self, app, mock_redis):
        """空值缓存防穿透"""
        from app.notifications.cache import NotificationCache
        with app.app_context():
            NotificationCache.set_empty(1)
            assert NotificationCache.get_unread_count(1) == 0
            assert NotificationCache.is_empty(1) is True


class TestNotificationEventHandlers:
    """通知事件处理函数单元测试"""

    def test_handle_comment_created_success(self, app, db_session, mock_redis):
        """测试评论事件处理函数创建通知"""
        from app.notifications.services import _handle_comment_created
        from tests.unit.factories import UserFactory
        with app.app_context():
            user = UserFactory()
            actor = UserFactory()
            _handle_comment_created({
                "user_id": user.id,
                "actor_id": actor.id,
                "type": "comment",
                "comment_id": 1,
                "post_id": 1,
                "content": "测试评论通知"
            })
            from app.notifications.models import Notification
            notif = Notification.query.filter_by(user_id=user.id).first()
            assert notif is not None
            assert notif.type == "comment"

    def test_handle_comment_created_invalid_user(self, app, db_session, mock_redis):
        """测试评论事件处理函数 - 用户不存在时不抛异常"""
        from app.notifications.services import _handle_comment_created
        with app.app_context():
            _handle_comment_created({
                "user_id": 999999,
                "actor_id": 888888,
                "type": "comment",
                "content": "测试"
            })

    def test_handle_like_created_success(self, app, db_session, mock_redis):
        """测试点赞事件处理函数创建通知（帖子）"""
        from app.notifications.models import Notification
        from app.notifications.services import _handle_like_created
        from tests.unit.factories import PostFactory, UserFactory
        with app.app_context():
            owner = UserFactory()
            actor = UserFactory()
            post = PostFactory(author=owner)
            _handle_like_created({
                "user_id": owner.id,
                "actor_id": actor.id,
                "type": "like",
                "post_id": post.id,
                "target_type": "post",
            })
            notif = Notification.query.filter_by(user_id=owner.id, type="like").first()
            assert notif is not None
            assert notif.resource_type == "post"
            assert notif.resource_id == post.id

    def test_handle_follow_created_success(self, app, db_session, mock_redis):
        """测试关注事件处理函数创建通知"""
        from app.notifications.models import Notification
        from app.notifications.services import _handle_follow_created
        from tests.unit.factories import UserFactory
        with app.app_context():
            followed = UserFactory()
            follower = UserFactory()
            _handle_follow_created({
                "user_id": followed.id,
                "actor_id": follower.id,
                "type": "follow",
            })
            notif = Notification.query.filter_by(user_id=followed.id, type="follow").first()
            assert notif is not None
            assert notif.resource_type == "user"

    def test_register_notification_event_handlers(self, app, mock_redis):
        """测试注册通知事件处理器"""
        from app.notifications.services import register_notification_event_handlers
        with app.app_context():
            register_notification_event_handlers()


