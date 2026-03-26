import pytest
from core.security import security_manager

class TestSecurityManager:
    """安全管理单元测试"""

    def test_encode_jwt_token(self, app):
        """测试JWT令牌生成"""
        user_id = 123456
        token = security_manager.generate_jwt_token(
            user_id=user_id, 
            token_type="access"
        )
        assert token is not None
        assert isinstance(token, str)

    def test_decode_jwt_token_success(self, app):
        """测试JWT令牌验证"""
        user_id = 123456
        token = security_manager.generate_jwt_token(
            user_id=user_id, 
            token_type="access"
        )
        payload = security_manager.verify_jwt_token(token)
        assert payload == user_id