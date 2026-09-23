import time
from functools import wraps

from prometheus_client import Counter, Gauge, Histogram

#----------HTTP层----------------
HTTP_REQUESTS = Counter(
    'weibo_http_requests_total',
    'Total Http requests',
    ['method', 'endpoint', 'status_code']
)
HTTP_LATENCY = Histogram(
    'weibo_http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

#======================DB层======================
DB_QUERY_LATENCY = Histogram(
    'weibo_db_query_duration_seconds',
    'DB query latency',
    ['operation', 'table'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)

#====================redis层=======================
REDIS_LATENCY = Histogram(
    'weibo_redis_operation_duration_seconds',
    'Redis operation latency',
    ['command'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5]
)
REDIS_HIT_RATE = Gauge(
    'weibo_redis_cache_hit_rate',
    'Redis cache hit rate(1=hit,0=miss)',
    ['cache_type']
)

#==================celery层=====================
CELERY_TASKS = Counter(
    'weibo_celery_tasks_total',
    'TOTAL Celery tasks',
    ['task_name', 'status']      # success, failure, published, publish_failed
)

CELERY_TASK_LATENCY = Histogram(
    'weibo_celery_task_duration_seconds',
    'Celery task execution latency',
    ['task_name'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0]
)

#=========================业务层========================
LIKE_OPERATIONS = Counter(
    'weibo_like_operations_total',
    'Like/unlike operations',
    ['action', 'result']  # action:create/delete, result:success/duplicate/error
)
POST_OPERATIONS = Counter(
    'weibo_post_operations_total',
    'Post CRUD operations',
    ['action', 'result']
)
FEED_OPERATIONS = Counter(
    'weibo_feed_operations_total',
    'Feed operations',
    ['action', 'result']
)
COMMENT_OPERATIONS = Counter(
    'weibo_comment_operations_total',
    'Comment operations',
    ['action', 'result']
)
FOLLOW_OPERATIONS = Counter(
    'weibo_follow_operations_total',
    'Follow/unfollow operations',
    ['action', 'result']
)
NOTIFICATION_OPERATIONS = Counter(
    'weibo_notification_operations_total',
    'Notification operations',
    ['action', 'result']
)
USER_OPERATIONS = Counter(
    'weibo_user_operations_total',
    'User auth/account operations',
    ['action', 'result']
)
CHAT_OPERATIONS = Counter(
    'weibo_chat_operations_total',
    'Chat (private message) operations',
    ['action', 'result']
)
RECONCILE_DIFF_COUNT = Gauge(
    'weibo_reconcile_diff_count',
    'Redis vs DB reconcile diff',
    ['resource_type']  # like, follow, feed, comment
)
DB_REPLICA_HEALTHY = Gauge(
    'weibo_db_replica_healthy',
    '从库健康状态(1健康/0不健康)',
    ['bind']
)
DB_REPLICA_FAILOVER = Counter(
    'weibo_db_replica_failover_total',
    '读操作从从库回落主库的次数',
    ['bind']
)

#=================装饰器==================================
def monitor_db(operation: str, table: str):
    """
    DB查询监控装饰器
    注意用法顺序：@staticmethod 在上，@monitor_db在下（靠近函数）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                DB_QUERY_LATENCY.labels(
                    operation=operation, table=table
                ).observe(time.perf_counter() - start)
        return wrapper
    return decorator


def monitor_redis(command: str):
    """Redis 操作监控装饰器(给LikeCache等用)"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                REDIS_LATENCY.labels(command=command).observe(
                    time.perf_counter() - start
                )
        return wrapper
    return decorator
