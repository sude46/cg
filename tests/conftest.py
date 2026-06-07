import sys
import time
from pathlib import Path 
import pytest
import logging
from unittest.mock import MagicMock
from flask import Flask
from sqlalchemy import text  
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import inspect
import traceback
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.factory import create_app
from core.database import db

# 尝试导入所有模型，并检查是否成功
try:
    from app.users.models import User
    from app.posts.models import Post
    from app.comments.models import Comment
    from app.follows.models import Follow
    from app.likes.models import Like
    from app.notifications.models import Notification
except Exception as e:
    sys.stderr.write(f"ERROR importing models: {e}\n")
    traceback.print_exc(file=sys.stderr)
    raise

# 模块级别检查模型注册
sys.stderr.write("=== Model registration at module level ===\n")
sys.stderr.write(f"Current db id: {id(db)}\n")
for model in [User, Post, Comment, Follow, Like, Notification]:
    sys.stderr.write(f"{model.__name__}: metadata is db.metadata? {model.metadata is db.metadata}\n")
    sys.stderr.write(f"  tables in its metadata: {list(model.metadata.tables.keys())}\n")
sys.stderr.write("=== End module level check ===\n\n")

# 关闭测试日志的冗余输出
logging.getLogger("flask.app").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

# ---------------------- 全局Fixture：Flask应用实例 ----------------------
@pytest.fixture(scope="session")
def app():
    app = create_app(config_name="testing")
    # 验证配置被正确加载
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:', \
        f"期望内存数据库，实际得到: {app.config['SQLALCHEMY_DATABASE_URI']}"
    
    with app.app_context():
        yield app
        db.session.remove()    

@pytest.fixture(scope="function")
def client(app):
    return app.test_client()



@pytest.fixture(scope="function")
def db_session(app):
    with app.app_context():
        db.create_all()
        from tests.unit import factories
        from tests.unit.factories import BaseFactory
        
        for name in dir(factories):
            obj = getattr(factories, name)
            if isinstance(obj, type) and issubclass(obj, BaseFactory):
                obj._meta.sqlalchemy_session = db.session
        
        yield db.session
        
        # 清理
        db.session.rollback()
        # 对于内存数据库，drop_all 其实不必要，但保持习惯
        db.drop_all()

class FakeRedisClient:
    """内存 dict 模拟 Redis，用于缓存层测试"""

    def __init__(self):
        self.store = {}
        self.expiry = {}

    def get(self, key):
        self._evict(key)
        return self.store.get(key)

    def setex(self, key, expire, value):
        self.store[key] = value
        if expire:
            self.expiry[key] = time.time() + expire
        return True

    def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                self.expiry.pop(key, None)
                count += 1
        return count

    def exists(self, key):
        self._evict(key)
        return 1 if key in self.store else 0

    def expire(self, key, ttl):
        if key in self.store:
            self.expiry[key] = time.time() + ttl
            return True
        return False

    def incrby(self, key, amount=1):
        val = int(self.store.get(key, 0)) + amount
        self.store[key] = str(val)
        return val

    incr = incrby

    def smembers(self, key):
        return self.store.get(key, set())

    def sadd(self, key, *members):
        if key not in self.store:
            self.store[key] = set()
        self.store[key].update(members)
        return len(members)

    def srem(self, key, *members):
        s = self.store.get(key, set())
        count = 0
        for m in members:
            if m in s:
                s.remove(m)
                count += 1
        return count

    def sismember(self, key, member):
        s = self.store.get(key, set())
        return member in s

    def scard(self, key):
        return len(self.store.get(key, set()))

    def zrevrange(self, key, start, end, withscores=False):
        items = self.store.get(key, {})
        sorted_items = sorted(items.items(), key=lambda x: x[1], reverse=True)
        slice_items = sorted_items[start:end + 1] if end != -1 else sorted_items[start:]
        if withscores:
            return slice_items
        return [item[0] for item in slice_items]

    def zadd(self, key, mapping, **kwargs):
        if key not in self.store:
            self.store[key] = {}
        self.store[key].update(mapping)
        return len(mapping)

    def zrem(self, key, *members):
        items = self.store.get(key, {})
        count = 0
        for m in members:
            if m in items:
                del items[m]
                count += 1
        return count

    def hget(self, key, field):
        d = self.store.get(key, {})
        return d.get(field)

    def hset(self, key, field, value):
        if key not in self.store:
            self.store[key] = {}
        self.store[key][field] = value
        return 1

    def hincrby(self, key, field, amount=1):
        if key not in self.store:
            self.store[key] = {}
        val = int(self.store[key].get(field, 0)) + amount
        self.store[key][field] = str(val)
        return val

    def scan_iter(self, match=None, count=None):
        if match is None:
            return iter(list(self.store.keys()))
        import fnmatch
        return iter(fnmatch.filter(self.store.keys(), match))

    def brpop(self, key, timeout=0):
        """EventBus 用 brpop 轮询消息队列"""
        return None

    def lpush(self, key, *values):
        """EventBus 用 lpush 发布事件"""
        return len(values)

    def pipeline(self):
        return self

    def setnx(self, key, value):
        if key not in self.store:
            self.store[key] = value
            return True
        return False

    def _evict(self, key):
        if key in self.expiry and time.time() > self.expiry[key]:
            del self.store[key]
            del self.expiry[key]


@pytest.fixture
def mock_redis(monkeypatch):
    """模拟 Redis 客户端（FakeRedisClient，内存存储）"""
    fake = FakeRedisClient()
    monkeypatch.setattr('utils.redis_util.RedisClient.get_conn', lambda for_write=False: fake)
    yield fake
