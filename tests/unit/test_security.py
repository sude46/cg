import uuid

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

    def test_password_hashing(self, app):
        """测试密码哈希与验证（bcrypt）"""
        from app.users.services.password_service import password_service
        plain = "MyPassword123!"
        hashed = password_service.hash_password(plain)

        assert hashed != plain
        assert password_service.verify_password(hashed, plain) is True
        assert password_service.verify_password(hashed, "wrong") is False

    def test_password_reuse_policy(self, app, db_session):
        """测试密码历史重用检测"""
        from app.users.repositories import user_repository
        from app.users.services import AuthService
        from app.users.services.password_service import password_service
        with app.app_context():
            username = f"reuse_{uuid.uuid4().hex[:8]}"
            email = f"{username}@example.com"
            password = "Orig1nal!"
            user = AuthService.register_user(username, email, password)["user"]
            user_entity = user_repository.get_by_id(user["id"])

            password_service.update_password(
                user_entity, "NewPass123!"
            )
            db_session.commit()

            assert password_service.is_password_reused(
                user_entity, password
            ) is True

    def test_jwt_expired_token(self, app):
        """测试过期 JWT 应被拒绝"""
        with app.app_context():
            token = security_manager.generate_jwt_token(
                user_id=123,
                token_type="access",
                expires_in=-1
            )
            assert security_manager.verify_jwt_token(token) is None

    def test_password_validator_complexity(self, app):
        """测试密码复杂度校验规则"""
        from core.security import password_validator
        weak = password_validator.validate("123")
        assert weak["is_valid"] is False
        strong = password_validator.validate("Str0ngPass!")
        assert strong["is_valid"] is True

    def test_email_validation(self, app):
        """测试邮箱格式校验"""
        import re
        EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        assert re.match(EMAIL_REGEX, "valid@example.com") is not None
        assert re.match(EMAIL_REGEX, "invalid-email") is None
