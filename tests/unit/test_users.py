import pytest
from app.users.services.auth_service import AuthService
from app.users.models import User
from app.common.exceptions import BusinessException, AuthenticationError, ValidationError
from tests.unit.factories import UserFactory
import uuid

class TestAuthService:
    """认证模块单元测试"""

    def test_create_user_success(self, app, db_session, mock_redis):
        """测试用户注册成功"""
        username = f"testuser_{uuid.uuid4().hex[:8]}"
        email = f"test_{uuid.uuid4().hex}@example.com"
        password = "pass1234"

        result = AuthService.register_user(username, email, password)

        assert result['message'] == '用户注册成功'
        assert 'user' in result
        user_data = result['user']
        assert user_data['username'] == username
        assert 'id' in user_data

        user = User.query.filter_by(username=username).first()
        assert user is not None
        assert user.username == username
        assert user.email == email

    def test_create_user_duplicate_username(self, app, db_session, mock_redis):
        """测试注册重复用户名（抛出异常）"""
        username = f"dupuser_{uuid.uuid4().hex[:8]}"
        email1 = f"{username}_1@example.com"
        password = "pass1234"
        AuthService.register_user(username, email1, password)

        email2 = f"{username}_2@example.com"
        with pytest.raises(ValidationError) as excinfo:
            AuthService.register_user(username, email2, "password123")
        assert "用户名已存在" in str(excinfo.value)

    def test_login_success(self, app, db_session, mock_redis):
        """测试用户登录成功"""
        username = f"testuser_{uuid.uuid4().hex[:8]}"
        email = f"login_{uuid.uuid4().hex}@example.com"
        password = "pass1234"
        AuthService.register_user(username, email, password)

        result = AuthService.authenticate_user(username, password)

        assert 'access_token' in result
        assert 'refresh_token' in result
        assert result['user']['username'] == username

    def test_login_wrong_password(self, app, db_session, mock_redis):
        """测试登录密码错误（抛出异常）"""
        username = f"testuser_{uuid.uuid4().hex[:8]}"
        email = f"wrong_{uuid.uuid4().hex}@example.com"
        password = "correct123"
        AuthService.register_user(username, email, password)

        with pytest.raises(AuthenticationError) as excinfo:
            AuthService.authenticate_user(username, "wrong_password")
        assert "用户名或密码错误" in str(excinfo.value)

    def test_create_user_duplicate_email(self, app, db_session, mock_redis):
        """测试重复邮箱注册应抛出异常"""
        with app.app_context():
            username = f"user1_{uuid.uuid4().hex[:8]}"
            email = f"dup_{uuid.uuid4().hex}@example.com"
            AuthService.register_user(username, email, "Pass1234!")
            username2 = f"user2_{uuid.uuid4().hex[:8]}"
            with pytest.raises(ValidationError) as excinfo:
                AuthService.register_user(username2, email, "Pass1234!")
            assert "邮箱已存在" in str(excinfo.value)

    def test_register_weak_password(self, app, db_session, mock_redis):
        """测试弱密码应该被拒绝"""
        with app.app_context():
            username = f"weak_{uuid.uuid4().hex[:8]}"
            email = f"{username}@example.com"
            with pytest.raises(ValidationError) as excinfo:
                AuthService.register_user(username, email, "123")
            assert "密码不符合要求" in str(excinfo.value)

    def test_login_locked_account(self, app, db_session, mock_redis):
        """测试多次失败后账户锁定"""
        with app.app_context():
            username = f"lock_{uuid.uuid4().hex[:8]}"
            email = f"{username}@example.com"
            password = "Correct123!"
            AuthService.register_user(username, email, password)

            for _ in range(5):
                with pytest.raises(AuthenticationError):
                    AuthService.authenticate_user(username, "wrong_password")

            with pytest.raises(AuthenticationError) as excinfo:
                AuthService.authenticate_user(username, password)
            assert "账户已锁定" in str(excinfo.value)

    def test_token_refresh(self, app, db_session, mock_redis):
        """测试刷新令牌返回新的access_token"""
        with app.app_context():
            username = f"refresh_{uuid.uuid4().hex[:8]}"
            email = f'{username}@example.com'
            user = AuthService.register_user(username, email, "Pass1234!")["user"]
            result = AuthService.refresh_token(user["id"])
            assert "access_token" in result
            assert result["token_type"] == "bearer"
            assert result["expires_in"] == 3600

    def test_get_current_user(self, app, db_session, mock_redis):
        """测试获取当前用户信息"""
        with app.app_context():
            username = f"current_{uuid.uuid4().hex[:8]}"
            email = f"{username}@example.com"
            user = AuthService.register_user(username, email, "Pass1234!")["user"]

            result = AuthService.get_current_user(user["id"])

            assert "user" in result
            assert result["user"]["username"] == username


class TestUserCache:
    """用户缓存层单元测试"""

    def test_set_and_get_profile(self, app, mock_redis):
        """用户资料缓存读写"""
        from app.users.cache import UserCache
        with app.app_context():
            data = {"id": 1, "username": "test"}
            UserCache.set_profile(1, data)
            assert UserCache.get_profile(1) == data

    def test_get_miss_returns_none(self, app, mock_redis):
        """未缓存返回 None"""
        from app.users.cache import UserCache
        with app.app_context():
            assert UserCache.get_profile(99999) is None

    def test_set_by_username(self, app, mock_redis):
        """用户名索引缓存"""
        from app.users.cache import UserCache
        with app.app_context():
            UserCache.set_by_username("testuser", 1)
            assert UserCache.get_by_username("testuser") == 1

    def test_set_by_email(self, app, mock_redis):
        """邮箱索引缓存"""
        from app.users.cache import UserCache
        with app.app_context():
            UserCache.set_by_email("test@test.com", 1)
            assert UserCache.get_by_email("test@test.com") == 1

    def test_recently_modified(self, app, mock_redis):
        """强一致标记"""
        from app.users.cache import UserCache
        with app.app_context():
            UserCache.mark_recently_modified(1, ttl=5)
            assert UserCache.is_recently_modified(1) is True

    def test_double_invalidate(self, app, mock_redis):
        """双重失效"""
        from app.users.cache import UserCache
        with app.app_context():
            UserCache.set_profile(1, {"id": 1})
            UserCache.double_invalidate(1, username="test", email="test@test.com")
            assert UserCache.get_profile(1) is None

    def test_preload_profiles(self, app, mock_redis):
        """批量预热"""
        from app.users.cache import UserCache
        with app.app_context():
            profiles = {1: {"id": 1}, 2: {"id": 2}}
            UserCache.preload_profiles([1, 2], profiles)
            assert UserCache.get_profile(1) == {"id": 1}
            assert UserCache.get_profile(2) == {"id": 2}
