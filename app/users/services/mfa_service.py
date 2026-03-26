import logging

logger = logging.getLogger(__name__)


class MFAService:
    def __init__(self, pyotp_lib=None):
        # 如果未提供 pyotp_lib，尝试导入 pyotp
        if pyotp_lib is None:
            try:
                import pyotp
                self.pyotp = pyotp
            except ImportError:
                logger.warning("pyotp not installed, MFA functionality will be disabled")
                self.pyotp = None
        else:
            self.pyotp = pyotp_lib
    
    def _check_pyotp(self):
        """检查 pyotp 是否可用"""
        if self.pyotp is None:
            raise RuntimeError("MFA functionality is disabled (pyotp not available)")
    
    def generate_secret(self):
        self._check_pyotp()
        return self.pyotp.random_base32(length=16)
    
    def verify_code(self, secret: str, code: str):
        if not secret or not code:
            return False
        self._check_pyotp()
        totp = self.pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    
    def provisioning_uri(self, secret: str, username: str, issuer: str = "App"):
        self._check_pyotp()
        return self.pyotp.totp.TOTP(secret).provisioning_uri(
            username=username,
            issuer_name=issuer
        )