"""事件总线 P0 行为测试：入队失败可见、无订阅者/重试耗尽进死信。"""


class TestEventBusPublish:
    def test_publish_enqueues_and_returns_true(self, app, mock_redis):
        from app.common.events import event_bus
        with app.app_context():
            ok = event_bus.publish('t.published', {'a': 1})
            assert ok is True
            assert mock_redis.llen('event_bus:queue') == 1

    def test_publish_failure_returns_false(self, app, monkeypatch):
        from app.common.events import event_bus
        monkeypatch.setattr(
            'utils.redis_util.RedisClient.get_conn', lambda for_write=False: None
        )
        with app.app_context():
            assert event_bus.publish('t.failed', {}) is False


class TestEventBusDispatch:
    def test_no_subscriber_goes_to_dead_letter(self, app, mock_redis):
        from app.common.events import event_bus
        with app.app_context():
            event_bus._dispatch(
                mock_redis, 't.no.sub', {},
                {'event': 't.no.sub', 'payload': {}, 'retry_count': 0},
            )
            assert mock_redis.llen('event_bus:dead_letter') == 1

    def test_handler_failure_retries_then_dead_letters(self, app, mock_redis):
        from app.common.events import event_bus

        def boom(payload):
            raise RuntimeError('boom')

        event_bus._subscribers['t.fail'] = [boom]
        try:
            with app.app_context():
                ev = {'event': 't.fail', 'payload': {}, 'retry_count': 0}
                event_bus._dispatch(mock_redis, 't.fail', {}, ev)
                assert ev['retry_count'] == 1
                assert mock_redis.llen('event_bus:queue') == 1

                ev2 = {'event': 't.fail', 'payload': {}, 'retry_count': 2}
                event_bus._dispatch(mock_redis, 't.fail', {}, ev2)
                assert mock_redis.llen('event_bus:dead_letter') == 1
        finally:
            event_bus._subscribers.pop('t.fail', None)

    def test_success_marks_handled(self, app, mock_redis):
        from app.common.events import event_bus
        seen = []
        event_bus._subscribers['t.ok'] = [lambda p: seen.append(p)]
        try:
            with app.app_context():
                event_bus._dispatch(
                    mock_redis, 't.ok', {'x': 1},
                    {'event': 't.ok', 'payload': {}, 'retry_count': 0},
                )
                assert seen == [{'x': 1}]
                assert mock_redis.llen('event_bus:queue') == 0
                assert mock_redis.llen('event_bus:dead_letter') == 0
        finally:
            event_bus._subscribers.pop('t.ok', None)
