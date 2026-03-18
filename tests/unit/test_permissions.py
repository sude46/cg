# tests/unit/test_permissions.py
import pytest
from app.permissions.services import PermissionService
from app.users.models import User

class TestPermissionService:
    """权限编解模块单元测试"""

    def test_encode_jwt_token(self, app):
        """测试JWT令牌加密"""
        # 执行加密
        user_id = 123456
        token = PermissionService.encode_token(user_id)

        # 断言结果
        assert token is not None
        assert isinstance(token, str)

    def test_decode_jwt_token_success(self, app):
        """测试JWT令牌解密成功"""
        # 先加密，再解密
        user_id = 123456
        token = PermissionService.encode_token(user_id)
        payload = PermissionService.decode_token(token)

        # 断言
        assert payload["user_id"] == user_id
        assert "exp" in payload  # 包含过期时间

    def test_decode_jwt_token_invalid(self, app):
        """测试解密无效令牌（抛出异常）"""
        invalid_token = "invalid_token_123456"
        with pytest.raises(Exception) as excinfo:
            PermissionService.decode_token(invalid_token)
        assert "无效令牌" in str(excinfo.value)