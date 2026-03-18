import time
from datetime import datetime, timedelta
from flask import current_app
import jwt as pyjwt


class PermissionService:
    """轻量的权限/令牌工具，用于测试环境。"""
    @staticmethod
    def encode_token(user_id: int) -> str:
        secret = current_app.config.get("JWT_SECRET_KEY")
        if not secret:
            raise RuntimeError("JWT_SECRET_KEY未配置")
        exp_minutes = current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", 30)
        from datetime import UTC
        payload = {
            "user_id": user_id,
            "exp": datetime.now(UTC) + timedelta(minutes=exp_minutes)
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")
        # PyJWT 返回 str in pyjwt>=2, bytes in some environments — normalize
        if isinstance(token, bytes):
            token = token.decode('utf-8')
        return token

    @staticmethod
    def decode_token(token: str) -> dict:
        secret = current_app.config.get("JWT_SECRET_KEY")
        if not secret:
            raise RuntimeError("JWT_SECRET_KEY未配置")
        try:
            payload = pyjwt.decode(token, secret, algorithms=["HS256"])
            return payload
        except Exception as e:
            raise Exception("无效令牌") from e
