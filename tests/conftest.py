import logging
import sys
from pathlib import Path

import pytest

# ---------------------- 项目路径注入 ----------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import db
from core.factory import create_app

# ---------------------- 日志降噪 ------------------------
logging.getLogger("flask.app").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("celery").setLevel(logging.WARNING)

# ---------------------- 模型注册检查（调试用）----------------------
try:
    from app.comments.models import Comment
    from app.follows.models import Follow
    from app.likes.models import Like
    from app.notifications.models import Notification
    from app.posts.models import Post
    from app.users.models import User
except Exception as e:
    import traceback
    sys.stderr.write(f"ERROR importing models: {e}\n")
    traceback.print_exc(file=sys.stderr)
    raise

# 模块级别模型绑定检查
sys.stderr.write("=== Model registration check ===\n")
for model in [User, Post, Comment, Follow, Like, Notification]:
    sys.stderr.write(
        f"{model.__name__}: metadata is db.metadata? {model.metadata is db.metadata}\n"
    )
sys.stderr.write("=== End check ===\n\n")


# ==============================================================================
# 核心 Fixture
# ==============================================================================

@pytest.fixture(scope="session")
def app():
    """Session 级 Flask 应用，测试配置（SQLite :memory:）"""
    app = create_app(config_name="testing")
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:', \
        f"期望内存数据库，实际: {app.config['SQLALCHEMY_DATABASE_URI']}"

    # Celery 同步模式（测试内联执行任务，不依赖 broker/worker）
    from core.celery_app import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    if 'celery' in app.extensions:
        celery = app.extensions['celery']
        celery.conf.task_always_eager = True
        celery.conf.task_eager_propagates = True

    # 单元测试停掉后台事件消费者：它与测试线程共用 SQLite 内存库连接，
    # 异步写通知会 detach 测试会话对象（事件处理逻辑本身由各测试直接调用验证）。
    from app.common.events import event_bus
    event_bus.stop()

    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture(scope="function")
def client(app):
    """函数级 HTTP 测试客户端"""
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app):
    """
    函数级数据库会话，自动建表 + 绑定 Factory + 清理。
    每个测试函数开始时都是干净的数据库。
    """
    with app.app_context():
        db.create_all()

        try:
            from tests.unit import factories
            from tests.unit.factories import BaseFactory
            for name in dir(factories):
                obj = getattr(factories, name)
                if isinstance(obj, type) and issubclass(obj, BaseFactory):
                    obj._meta.sqlalchemy_session = db.session
        except ImportError:
            pass

        yield db.session

        db.session.rollback()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def mock_redis(monkeypatch):
    """
    注入 FakeRedisClient 替换真实 Redis。
    工具类从 tests.utils.fake_redis 导入，避免 conftest 臃肿。
    """
    from tests.utils.fake_redis import FakeRedisClient
    fake = FakeRedisClient()
    monkeypatch.setattr(
        'utils.redis_util.RedisClient.get_conn',
        lambda for_write=False: fake
    )
    yield fake
