import logging

from utils.security_utils import decrypt_mfa_secret, encrypt_mfa_secret

logger = logging.getLogger(__name__)


class MFAService:
    def __init__(self, pyotp_lib=None):
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
        if self.pyotp is None:
            raise RuntimeError("MFA functionality is disabled (pyotp not available)")

    def generate_secret(self):
        """生成明文 TOTP Secret（调用方自行 encrypt 后存入 DB）

        TOTP 要求至少 160 bits（base32 32 字符），length=16 会被 pyotp 拒绝。
        """
        self._check_pyotp()
        return self.pyotp.random_base32(length=32)

    def encrypt_secret(self, plain_secret: str) -> str:
        """加密后再存储到 DB"""
        return encrypt_mfa_secret(plain_secret)

    def decrypt_secret(self, encrypted_secret: str) -> str:
        """从 DB 读取后解密为明文"""
        return decrypt_mfa_secret(encrypted_secret)

    def verify_code(self, encrypted_secret: str, code: str) -> bool:
        """校验 TOTP 验证码（自动解密）"""
        if not encrypted_secret or not code:
            return False
        self._check_pyotp()
        try:
            plain_secret = decrypt_mfa_secret(encrypted_secret)
            totp = self.pyotp.TOTP(plain_secret)
            return totp.verify(code, valid_window=1)
        except Exception as e:
            logger.error(f'MFA 验证解密失败: {e}')
            return False

    def provisioning_uri(self, encrypted_secret: str, username: str, issuer: str = "App") -> str:
        """生成二维码 URI（自动解密）"""
        self._check_pyotp()
        plain_secret = decrypt_mfa_secret(encrypted_secret)
        return self.pyotp.totp.TOTP(plain_secret).provisioning_uri(
            name=username,
            issuer_name=issuer
        )
