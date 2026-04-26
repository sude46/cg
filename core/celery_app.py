'''
Celery应用实例配置
'''
from celery import Celery
from config import get_config

def make_celery(app_name='weibo'):
    celery=Celery(
        app_name,
        broker=get_config.REDIS_URL,             #redis作为消息队列
        backend=get_config.REDIS_URL,           #redis存储结果
        include=[
            'app.tasks.feed_tasks',
            'app.tasks.notification_tasks',
            'app.tasks.email_tasks',
            'app.tasks.search_tasks',
            'app.tasks.media_tasks',
            'app.tasks.data_tasks',
            'app.tasks.cleanup_tasks',
            'app.tasks.export_tasks',
        ]
    )
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='Asia/Shanghai',
        enable_utc=True,
        task_time_limit=3600,
        worker_prefetch_multiplier=4,
        task_default_queue='default',
        task_routes={
            'app.tasks.emails_tasks.*':{'queue':'email'},
            'app.tasks.media_tasks.*':{'queue':'media'},
            'app.tasks.search_tasks.*':{'queue':'search'},
            'app.tasks.data_tasks.*':{'queue':'data'},
        },
        beat_schedule={
            #定时任务：每天凌晨清理过去缓存
            'clean-expired-cache':{
                'task':'app.task.cleanup_task.clean_expired_cache',
                'schedule':86400.0,
                'args':(),
            },
             # 定时任务：每小时计算热榜
            'calculate-hot-posts': {
                'task': 'app.tasks.data_tasks.calculate_hot_posts',
                'schedule': 3600.0,
            },

        }            
    )
    return celery
celery_app=make_celery()