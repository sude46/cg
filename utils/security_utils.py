from markupsafe import escape
from flask import current_app
import base64
import os

def html_escape(content):
    """
    HTML转义（防止XSS）
    :param content: 待转义内容（字符串/字典/列表）
    :return: 转义后的内容
    """
    if isinstance(content, str):
        return escape(content)
    elif isinstance(content, dict):
        return {k: html_escape(v) for k, v in content.items()}
    elif isinstance(content, list):
        return [html_escape(item) for item in content]
    else:
        return content


def _get_fernet():
    """延迟获取 Fernet 实例（避免启动时依赖 app context）"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError("cryptography 未安装: pip install cryptography")

    key = current_app.config.get('MFA_ENCRYPTION_KEY')
    if not key:
        raise RuntimeError("MFA_ENCRYPTION_KEY 未配置")
    if isinstance(key, str):
        key = key.encode('utf-8')
    return Fernet(key)


def encrypt_mfa_secret(plain_secret: str) -> str:
    """加密 MFA Secret 后再存入 DB"""
    f = _get_fernet()
    return f.encrypt(plain_secret.encode('utf-8')).decode('utf-8')


def decrypt_mfa_secret(encrypted_secret: str) -> str:
    """从 DB 取出后解密为明文 TOTP Secret"""
    f = _get_fernet()
    return f.decrypt(encrypted_secret.encode('utf-8')).decode('utf-8')


def generate_mfa_encryption_key() -> str:
    """初始化时生成一次，写入 .env: MFA_ENCRYPTION_KEY=xxx"""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode('utf-8')
