import time

from celery import Task

from core.metrics import CELERY_TASK_LATENCY, CELERY_TASKS

# worker 进程内只创建一次 Flask app
_flask_app = None


def _get_flask_app():
    """惰性创建 Flask app，避免导入期循环依赖"""
    global _flask_app
    if _flask_app is None:
        from app import create_app
        _flask_app = create_app()
    return _flask_app


class ContextTask(Task):
    """为每个任务注入 Flask application context（DB/Redis 单例依赖它）"""

    abstract = True

    def __call__(self, *args, **kwargs):
        app = _get_flask_app()
        with app.app_context():
            return super().__call__(*args, **kwargs)


class MonitoredTask(ContextTask):
    '''celery控制基类，自动埋点任务执行指标'''

    def __call__(self, *args, **kwargs):
        start = time.time()
        try:
            result = super().__call__(*args, **kwargs)
            CELERY_TASKS.labels(task_name=self.name, status='success').inc()
            return result
        except Exception:
            CELERY_TASKS.labels(task_name=self.name, status='failure').inc()
            raise
        finally:
            CELERY_TASK_LATENCY.labels(task_name=self.name).observe(time.time() - start)
