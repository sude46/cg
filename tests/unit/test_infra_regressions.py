"""针对端到端联调挖出的三个基础设施 bug 的回归测试。

- ES 客户端断开后重连（core/es_client.py 的 connect 读取 ES_HOST_LIST）
- Celery shared_task 必须绑定到项目 app 并使用 default 队列
- worker 的 import 顺序不能触发 feed_tasks 循环导入

这些用例不依赖 app/DB/Redis fixture，可在无外部服务的环境运行。
"""
import os
import subprocess
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_es_client_reconnect_resolves_host_list(monkeypatch):
    """ES 断开后重连：connect() 必须实例化配置类并取到 ES_HOST_LIST 列表。"""
    import core.es_client as mod
    from core.es_client import ESClient

    class FakeES:
        def __init__(self, hosts):
            # 旧代码会把 @property 对象当 hosts 传进来（'property' object is not iterable）
            assert isinstance(hosts, list), f"hosts 必须是 list，实际为 {type(hosts)}"
            self.hosts = hosts

        def options(self, **kwargs):
            return self

        def ping(self):
            return True

        def info(self):
            return {"version": {"number": "8.11.0"}}

    class FakeConfigClass:
        ELASTICSEARCH_ENABLED = True
        ELASTICSEARCH_TIMEOUT = 30

        @property
        def ES_HOST_LIST(self):
            return ["http://es:9200"]

    monkeypatch.setattr(mod, "Elasticsearch", FakeES)
    monkeypatch.setattr(mod, "get_config", lambda *a, **k: FakeConfigClass)

    ESClient._instance = None
    client = ESClient()
    client._es = None  # 模拟断开
    assert client.connect() is True
    assert client._es is not None


def test_celery_uses_project_app_for_shared_task():
    """shared_task 必须解析到项目 Celery app，且默认队列为 default。"""
    from core.celery_app import celery_app

    assert celery_app.conf.task_default_queue == "default"

    import tasks.like_tasks  # noqa: F401 触发注册
    task = celery_app.tasks["tasks.like_tasks.async_like_to_do"]
    assert task.app is celery_app


def test_web_boot_sets_celery_default_app():
    """仅 import core.factory（模拟 Web 启动）就应把项目 app 设为默认 app。

    这是 shared_task.delay 路由到 default 队列的前提。
    """
    code = (
        "import core.factory;"
        "import celery;"
        "from core.celery_app import celery_app;"
        "assert celery.current_app._get_current_object() is celery_app, celery.current_app;"
        "assert celery_app.conf.task_default_queue == 'default';"
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_worker_import_order_no_circular():
    """worker 的 include 列表按此顺序导入时不应触发循环导入。"""
    code = (
        "import tasks.feed_tasks;"
        "import tasks.search_tasks;"
        "import tasks.like_tasks;"
        "import tasks.notification_tasks;"
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_db_router_falls_back_to_master(monkeypatch):
    """从库探测失败时，读会话必须回落主库并标记从库失败。"""
    import core.db_router as mod
    from core import db

    class FakeApp:
        config = {'SQLALCHEMY_BINDS': {'replica': 'mysql+pymysql://u:p@h/db'}}

    mod.db_router.init_app(FakeApp())

    def boom(*args, **kwargs):
        raise RuntimeError('replica down')

    monkeypatch.setattr(db, 'get_engine', boom)

    session = mod.db_router.get_read_session()
    assert session is db.session
    assert mod.db_router._state['replica']['fail_count'] >= 1
