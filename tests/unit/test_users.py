import pytest
from app.users.services import AuthService
from app.users.models import User
from app.common.exceptions import BusinessException, AuthenticationError, ValidationError
from tests.unit.factories import UserFactory
import uuid  # 用于生成唯一邮箱

class TestAuthService:
    """认证模块单元测试"""

    def test_create_user_success(self, app,db_session, mock_redis):
        """测试用户注册成功"""
        # 1. 准备测试数据（使用唯一邮箱避免冲突）
        username = f"testuser_{uuid.uuid4().hex[:8]}"
        email = f"test_{uuid.uuid4().hex}@example.com"  # 生成唯一邮箱
        password = "pass1234"

        # 2. 执行注册逻辑
        result = AuthService.register_user(username, email, password)

        # 3. 断言结果
        assert result['message'] == '用户注册成功'
        assert 'user' in result
        user_data = result['user']
        assert user_data['username'] == username
        assert 'id' in user_data

        # 验证数据库中已创建用户
        user = User.query.filter_by(username=username).first()
        assert user is not None
        assert user.username == username
        assert user.email == email

    def test_create_user_duplicate_username(self, app,db_session, mock_redis):
        """测试注册重复用户名（抛出异常）"""
        # 1. 先创建一个用户（使用唯一邮箱）
        username = f"dupuser_{uuid.uuid4().hex[:8]}"   
        email1 = f"{username}_1@example.com"
        password="pass1234"
        AuthService.register_user(username, email1,password)

        # 2. 尝试使用相同用户名但不同邮箱注册，应抛出 ValidationError
        email2 = f"{username}_2@example.com"
        with pytest.raises(ValidationError) as excinfo:
            AuthService.register_user(username, email2, "password123")
        assert "用户名已存在" in str(excinfo.value)

    def test_login_success(self, app,db_session, mock_redis):
        """测试用户登录成功"""
        # 1. 准备测试数据：注册一个用户（使用唯一邮箱）
        username = f"testuser_{uuid.uuid4().hex[:8]}"
        email = f"login_{uuid.uuid4().hex}@example.com"
        password = "pass1234"
        AuthService.register_user(username, email, password)

        # 2. 执行登录逻辑（使用 authenticate_user）
        result = AuthService.authenticate_user(username, password)

        # 3. 断言结果
        assert 'access_token' in result
        assert 'refresh_token' in result
        assert result['user']['username'] == username

    def test_login_wrong_password(self, app,db_session, mock_redis):
        """测试登录密码错误（抛出异常）"""
        # 1. 准备测试数据：注册用户
        username = f"testuser_{uuid.uuid4().hex[:8]}"
        email = f"wrong_{uuid.uuid4().hex}@example.com"
        password = "correct123"
        AuthService.register_user(username, email, password)

        # 2. 使用错误密码登录，应抛出 AuthenticationError
        with pytest.raises(AuthenticationError) as excinfo:
            AuthService.authenticate_user(username, "wrong_password")
        assert "用户名或密码错误" in str(excinfo.value)
