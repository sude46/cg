from celery import Task
from core.metrics import CELERY_TASKS,CELERY_TASK_LATENCY
import time

class MonitoredTask(Task):
    '''celery控制基类，自动埋点任务执行指标'''
    def __call__(self,*args,**kwargs):
        start=time.time()
        try:
            result=super().__call__(*args,**kwargs)
            CELERY_TASKS.labels(task_name=self.name,status='success').inc()
            return result
        except Exception:
            CELERY_TASKS.labels(task_name=self.name,status='failure').inc()
            raise
        finally:
            CELERY_TASK_LATENCY.labels(task_name=self.name).observe(time.time()-start)

