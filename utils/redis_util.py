# utils/redis_util.py
import os
import redis
from flask import current_app


class RedisClient:
    """Redis工具类（单例、延迟初始化）。

    注意：不要在模块导入阶段访问 `current_app`（会在测试导入阶段抛出
    "Working outside of application context"）。连接会在首次使用时或显式
    调用 `init_app(app)` 时建立。
    """
    _instance = None
    _conn = None
    _url = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def init_app(cls, app):
        """显式用 app 初始化连接（推荐在 create_app 中调用）。"""
        cls._url = app.config.get("REDIS_URL") or os.environ.get("REDIS_URL")
        cls._ensure_conn()

    @classmethod
    def _ensure_conn(cls):
        if cls._conn is None:
            url = cls._url
            # 如果在请求上下文中且未显式设置 URL，尝试从 current_app 读取
            if not url:
                try:
                    url = current_app.config.get("REDIS_URL")
                except RuntimeError:
                    # 未在 app context 中且未配置 URL，降级为 None
                    url = None

            if not url:
                # 不阻塞导入阶段；后续方法会检查 _conn 并报错或降级
                return

            cls._conn = redis.Redis.from_url(url, decode_responses=True)

    def add_blacklist(self, token, expire_seconds):
        self._ensure_conn()
        if not self._conn:
            raise RuntimeError("Redis 未配置，请在应用工厂中调用 RedisClient.init_app(app) 或设置 REDIS_URL")
        self._conn.setex(name=f"jwt_blacklist:{token}", time=expire_seconds, value="invalid")

    def is_blacklisted(self, token):
        self._ensure_conn()
        if not self._conn:
            return False
        return self._conn.exists(f"jwt_blacklist:{token}") == 1


# 导出单例（不会在导入时创建连接）
redis_client = RedisClient()