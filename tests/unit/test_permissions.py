import pytest

from app.permissions.services import PermissionService


class TestPermissionService:
    """权限/JWT模块单元测试"""

    def test_encode_token(self, app):
        """测试PermissionService生成JWT"""
        with app.app_context():
            token = PermissionService.encode_token(user_id=123456)
            assert token is not None
            assert isinstance(token, str)
            assert len(token) > 20

    def test_decode_token_success(self, app):
        """测试解码有效JWT返回正确的user_id"""
        with app.app_context():
            user_id = 123456
            token = PermissionService.encode_token(user_id=user_id)
            payload = PermissionService.decode_token(token)
            assert payload["user_id"] == user_id

    def test_decode_token_invalid(self, app):
        """测试解码无效JWT抛出异常"""
        with app.app_context():
            with pytest.raises(Exception) as excinfo:
                PermissionService.decode_token("invalid.token.here")
            assert "无效令牌" in str(excinfo.value)

    def test_encode_decode_roundtrip(self, app):
        """测试编码解码往返一致性"""
        with app.app_context():
            user_id = 789
            token = PermissionService.encode_token(user_id)
            payload = PermissionService.decode_token(token)
            assert payload["user_id"] == user_id
            assert "exp" in payload
