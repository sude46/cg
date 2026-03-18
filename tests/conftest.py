import sys
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

@pytest.fixture
def mock_redis():
    """模拟Redis客户端的fixture（替换真实Redis）"""
    mock_redis_client = MagicMock()
    mock_redis_client.get.return_value = None
    mock_redis_client.set.return_value = True
    mock_redis_client.delete.return_value = 1
    mock_redis_client.expire.return_value = True
    yield mock_redis_client
