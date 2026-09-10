'''
Celery应用实例配置
'''
from celery import Celery
from config import get_config

def make_celery(app_name='weibo'):

    config_calss=get_config()
    config=config_calss()
    celery=Celery(
        app_name,
        broker=config.CELERY_BROKER_URL,             #redis作为消息队列
        backend=config.CELERY_RESULT_BACKEND,           #redis存储结果
        include=[
            'tasks.like_tasks',
            'tasks.like_reconcile',
            'tasks.feed_tasks',
            'tasks.post_tasks',
            'tasks.post_reconcile',
            'tasks.user_tasks',
            'tasks.user_reconcile',
            'tasks.notification_tasks',
            'tasks.comment_reconcile',
            'tasks.data_tasks',
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
            'tasks.like_tasks.*':{'queue':'like'},
        },
        beat_schedule={
            'reconcile-likes': {
                'task': 'tasks.like_reconcile.reconcile_like_counts',
                'schedule': 300.0,
                'args': ('post', 500),
            },
            'reconcile-posts': {       # 新增
            'task': 'tasks.post_reconcile.reconcile_post_cache',
            'schedule': 300.0,
            'args': (500,),
            },
            'calculate-hot-posts': {
            'task': 'tasks.data_tasks.calculate_hot_posts',
            'schedule': 3600.0,  # 1 小时
            'args': ('daily', 1000),
            },
            'reconcile-hot-comments': {
            'task': 'tasks.comment_reconcile.reconcile_hot_comments',
            'schedule': 600.0,  # 10 分钟
            'args': (50,),
            },
            'reconcile-user-cache': {
            'task': 'tasks.user_reconcile.reconcile_user_cache',
            'schedule': 600.0,  # 10 分钟
            'args': (500,),
            },

        }            
    )
    return celery
celery_app=make_celery()