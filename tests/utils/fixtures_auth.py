"""tests/utils/fixtures_auth.py
================
认证辅助 Fixture，从 conftest 拆出来，避免核心文件膨胀。
"""
import uuid
import pytest

@pytest.fixture
def auth_headers(app,db_session):
    '''
    返回一个生成JWT认证头函数
    用法：
    headers=auth_headers(user_id=1)
    client.get('/api/users/me',headers=headers)
    '''
    try:
        from flask_jwt_extended import create_access_token
        from app.users.models import User
    except ImportError:
        yield lambda **kwargs:{}
        return 
    def _make_headers(user_id=None,username="testuser",email="test@test.com"):
        if user_id is None:
            user=User(username=username,email=email)
            user.password_hash="fake_hash"
            db_session.add(user)
            db_session.commit()
            user_id=user.id

        token=create_access_token(identity=str(user_id))
        return {'Authorization':f'Bearer{token}'}

    yield _make_headers


@pytest.fixture
def authenticated_client(client,auth_headers):
    '''
    包装test_client,自动携带JWT
    用法：
    ac=authenticated_client(user_id=1)
    resp=ac.get('/api/users/me')

    '''
    class AC:
        def __init__(self,c,headers):
            self.c=c
            self.headers=headers
        def _merge(self,c,headers):
            h=kwargs.pop('headers'.{})
            h.update(self.headers)
            kwargs['headers']=h
            return kwargs
        def get(self,url,**kw):
            return self.c.get(url,**self._merge(kw))
        def post(self,url,**kw):
            return self.c.post(url,**self._merge(kw))
        def put(self,url,**kw):
            return self.c.put(url,**self._merge(kw))
        def delete(self,url,**kw):
            return self.c.delete(url,**self._merge(kw))
        def patch(self,url,**kw):
            return self.c.patch(url,**self._merge(kw))
        def _factory(user_id=None,**kw):
            return _AC(client,auth_headers(user_id=user_id,**kw))
        yield _factory


@pytest.fixture
def test_user(db_session):
    '''快速创建一个标准测试用户'''
    from app.users.models import User
    user=User(username="testuser",email="test@test.com")
    user.password_hash="fake_hash"
    db_session.add(user)
    db.session.commit()
    return user

@pytest.fixture
def test_user_factory(db_session):
    '''批量创建测试用户的工厂函数'''
    from app.users.models import User

    def _factory(username=None,emial=None,**kwargs):
        suffix=str(uuid.uuid4())[:8]
        username=username or f"user_{suffix}"
        email=eamil or f"{username}@test.com"
        user=User(username=username,email=email,**kwargs)
        user.password_hash="fake_hash"
        db_session.add(user)
        db_session.commit()
        return user
    yield _factory


