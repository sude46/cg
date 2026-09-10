# utils/redis_util.py
import os
import redis
from flask import current_app

import os
import redis
from redis.sentinel import Sentinel


class RedisClient:
    _instance = None
    _master_conn = None
    _slave_conn = None
    _config = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def init_app(cls, app):
        cls._config = {
            'url': app.config.get("REDIS_URL") or os.environ.get("REDIS_URL"),
            'host': app.config.get("REDIS_HOST", "localhost"),
            'port': app.config.get("REDIS_PORT", 6379),
            'db': app.config.get("REDIS_DB", 0),
            'password': app.config.get("REDIS_PASSWORD") or None,
            'sentinel_hosts': app.config.get("REDIS_SENTINEL_HOST", ""),
            'master_name': app.config.get("REDIS_SENTINEL_MASTER_NAME", "mymaster"),
            'socket_timeout': app.config.get("REDIS_SOCKET_TIMEOUT", 2),
            'decode_responses': app.config.get("REDIS_DECODE_RESPONSES", True),
        }
        cls._ensure_conns()
        app.config['REDIS_CLIENT'] = cls._slave_conn or cls._master_conn

    @classmethod
    def _init_sentinel(cls):
        hosts_str = cls._config.get('sentinel_hosts', '')
        if not hosts_str:
            return None
        hosts = []
        for h in hosts_str.split(","):
            h = h.strip()
            if not h:
                continue
            if ":" in h:
                host, port = h.rsplit(":", 1)
                hosts.append((host, int(port)))
            else:
                hosts.append((h, 26379))
        if not hosts:
            return None
        return Sentinel(
            hosts,
            socket_timeout=cls._config['socket_timeout'],
            socket_connect_timeout=cls._config['socket_timeout'],
            password=cls._config['password'],
            decode_responses=cls._config['decode_responses'],
        )

    @classmethod
    def _ensure_conns(cls):
        if cls._master_conn is not None:
            return
        try:
            sentinel = cls._init_sentinel()
            if sentinel:
                cls._master_conn = sentinel.master_for(
                    cls._config['master_name'],
                    socket_timeout=cls._config['socket_timeout'],
                )
                cls._slave_conn = sentinel.slave_for(
                    cls._config['master_name'],
                    socket_timeout=cls._config['socket_timeout'],
                )
            else:
                url = cls._config.get('url')
                if url:
                    conn = redis.Redis.from_url(
                        url,
                        decode_responses=cls._config['decode_responses'],
                        socket_timeout=cls._config['socket_timeout'],
                    )
                else:
                    conn = redis.Redis(
                        host=cls._config['host'],
                        port=cls._config['port'],
                        db=cls._config['db'],
                        password=cls._config['password'],
                        decode_responses=cls._config['decode_responses'],
                        socket_timeout=cls._config['socket_timeout'],
                    )
                cls._master_conn = conn
                cls._slave_conn = conn
            cls._master_conn.ping()
        except Exception as e:
            import warnings
            warnings.warn(f"Redis 连接失败: {e}", UserWarning)
            cls._master_conn = None
            cls._slave_conn = None

    @classmethod
    def get_conn(cls, for_write=False):
        if for_write:
            return cls._master_conn
        return cls._slave_conn or cls._master_conn

    def add_blacklist(self, token, expire_seconds):
        conn = self.__class__.get_conn(for_write=True)
        if not conn:
            raise RuntimeError("Redis 未配置")
        conn.setex(name=f"jwt_blacklist:{token}", time=expire_seconds, value="invalid")

    def is_blacklisted(self, token):
        conn = self.__class__.get_conn(for_write=False)
        if not conn:
            return False
        return conn.exists(f"jwt_blacklist:{token}") == 1


redis_client = RedisClient()
