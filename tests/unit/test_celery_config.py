"""FIX-09: Celery 必须 late ack，worker 崩溃后任务可重投。"""


def test_celery_late_ack_config():
    from core.celery_app import celery_app

    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_track_started is True


def test_celery_visibility_timeout_covers_task_time_limit():
    """Redis broker 的 visibility_timeout 要大于任务最长执行时间，避免运行中被重投。"""
    from core.celery_app import celery_app

    visibility = (celery_app.conf.broker_transport_options or {}).get(
        'visibility_timeout', 0
    )
    assert visibility > celery_app.conf.task_time_limit
