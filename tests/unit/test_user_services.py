import pytest
from app.common.exceptions import ValidationError


class TestAccountLockService:
    """账户锁定服务单元测试"""

    def test_is_locked_false_initially(self, app, mock_redis):
        from app.users.services.account_service import AccountLockService
        with app.app_context():
            assert AccountLockService.is_locked(1) is False

    def test_record_failed_attempt_locks_after_threshold(self, app, mock_redis):
        from app.users.services.account_service import AccountLockService
        with app.app_context():
            for _ in range(AccountLockService.MAX_LOGIN_FAILS):
                AccountLockService.record_failed_attempt(1)
            assert AccountLockService.is_locked(1) is True

    def test_reset_attempts(self, app, mock_redis):
        from app.users.services.account_service import AccountLockService
        with app.app_context():
            AccountLockService.record_failed_attempt(1)
            AccountLockService.reset_attempts(1)
            assert AccountLockService.is_locked(1) is False

    def test_lock_key_exists(self, app, mock_redis):
        from app.users.services.account_service import AccountLockService
        with app.app_context():
            for _ in range(AccountLockService.MAX_LOGIN_FAILS):
                AccountLockService.record_failed_attempt(1)
            key = AccountLockService._lock_key(1)
            from core.redis_cache import redis_cache
            assert redis_cache.exists(key) > 0


class TestMFAService:
    """多因素认证服务单元测试"""

    def test_generate_secret(self, app):
        from app.users.services.mfa_service import MFAService
        svc = MFAService()
        secret = svc.generate_secret()
        assert secret is not None
        assert len(secret) > 0

    def test_encrypt_decrypt_secret(self, app):
        from app.users.services.mfa_service import MFAService
        svc = MFAService()
        plain = svc.generate_secret()
        encrypted = svc.encrypt_secret(plain)
        assert encrypted != plain
        decrypted = svc.decrypt_secret(encrypted)
        assert decrypted == plain

    def test_verify_code_invalid_returns_false(self, app):
        from app.users.services.mfa_service import MFAService
        svc = MFAService()
        assert svc.verify_code("invalid_encrypted_secret", "123456") is False

    def test_provisioning_uri(self, app):
        from app.users.services.mfa_service import MFAService
        svc = MFAService()
        secret = svc.generate_secret()
        encrypted = svc.encrypt_secret(secret)
        uri = svc.provisioning_uri(encrypted, "testuser")
        assert uri.startswith("otpauth://")


class TestPasswordService:
    """密码服务单元测试"""

    def test_hash_and_verify(self, app, db_session, mock_redis):
        from app.users.services.password_service import PasswordService
        svc = PasswordService()
        hashed = svc.hash_password("MyP@ss123")
        assert svc.verify_password(hashed, "MyP@ss123") is True
        assert svc.verify_password(hashed, "WrongPassword") is False

    def test_update_password(self, app, db_session, mock_redis):
        from app.users.services.password_service import PasswordService
        from tests.unit.factories import UserFactory
        svc = PasswordService()
        with app.app_context():
            user = UserFactory()
            user.password_hash = svc.hash_password("OldPass123!")
            db_session.commit()
            svc.update_password(user, "NewPass456!")
            assert svc.verify_password(user.password_hash, "NewPass456!") is True


class TestTokenService:
    """Token管理服务单元测试"""

    def test_generate_and_verify_reset_token(self, app):
        from app.users.services.token_service import TokenService
        with app.app_context():
            token = TokenService.generate_tokens(123)
            assert token is not None
            assert isinstance(token, str)
            result = TokenService.verify_reset_token(token)
            assert result == 123

    def test_verify_invalid_token_returns_none(self, app):
        from app.users.services.token_service import TokenService
        with app.app_context():
            result = TokenService.verify_reset_token("invalid.token.here")
            assert result is None
