"""tests/utils/fixtures_mock.py
================
外部依赖 Mock Fixture（ES、EventBus、Celery、Mail）。
独立文件，按需使用。
"""
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_es(monkeypatch):
    """Mock Elasticsearch,搜索降级为DB查询"""
    fake=MagicMock()
    fake.search.return_value={
            'hits':{'total':{'value':0,'relation':'eq'},'hits':[]},
            'took':1,'timed_out':False
            }
    fake.index.return_value={'result':'created','_id':'mock-id'}
    fake.delete.return_value={'result':'deleted'}
    fake.update.return_value={'result':'updated'}
    fake.exists.return_value=False
    fake.bulk.return_value={'errors':False,'items':[]}

    for path in [
            'utils.es_utils.es_client',
            'core.extensions.es',
            'app.posts.search.es',
            'app.search.es'
            ]:
        try:
            monkeypatch.setattr(path,fake)
        except Exception:
            pass
    yield fake


@pytest.fixture
def mock_event_bus(monkeypatch):
    '''Mock事件总线，验证publish调用'''
    fake=MagicMock()
    fake.publish.return_value=True
    fake.subscribe.return_value=True
    fake.listen.return_value=iter([])

    for path in [
            'utils.event_bus.event_bus',
            'utils.event_bus.EventBus',
            'core.event_bus.event_bus',
            ]:
        try:
            monkeypatch.setattr(path,fake)
        except Exception:
            pass
    yield fake

@pytest.fixture
def mock_celery(app,monkeypatch):
    '''
    Celery同步模式+delay/apply_Async兜底mock

    '''
    if 'celery' in app.extensions:
        celery = app.extensions['celery']
        celery.conf.task_always_eager = True
        celery.conf.task_eager_propagates = True

    modules = [
        'tasks.like_tasks', 'tasks.post_tasks', 'tasks.comment_tasks',
        'tasks.feed_tasks', 'tasks.notification_tasks',
        'tasks.reconcile_tasks', 'tasks.search_tasks',
    ]
    for mod in modules:
        for attr in ['delay', 'apply_async']:
            try:
                monkeypatch.setattr(f'{mod}.{attr}', MagicMock())
            except Exception:
                pass
    yield True

@pytest.fixture
def mock_mail(app, monkeypatch):
    """Mock 邮件，验证测试环境 MAIL_SUPPRESS_SEND=True"""
    assert app.config.get('MAIL_SUPPRESS_SEND') is True, \
        "测试环境必须设置 MAIL_SUPPRESS_SEND=True"
    fake = MagicMock()
    fake.send = MagicMock()
    try:
        monkeypatch.setattr('utils.mail_util.mail', fake)
    except Exception:
        pass
    yield fake

