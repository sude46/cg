"""事件总线测试：入队失败可见、无订阅者/重试耗尽进死信、BLMOVE+ack+reaper 可靠队列。"""


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


class TestEventBusReliableQueue:
    def test_claim_and_ack(self, app, mock_redis):
        from app.common.events import event_bus
        with app.app_context():
            event_bus.publish('t.claim', {'n': 1})
            raw = event_bus._claim(mock_redis)
            assert raw is not None
            assert mock_redis.llen('event_bus:queue') == 0
            assert mock_redis.llen('event_bus:processing') == 1
            assert mock_redis.hgetall('event_bus:processing:ts')

            event_bus._ack(mock_redis, raw)
            assert mock_redis.llen('event_bus:processing') == 0
            assert mock_redis.hgetall('event_bus:processing:ts') == {}

    def test_reap_stale_requeues(self, app, mock_redis):
        from app.common.events import event_bus
        with app.app_context():
            raw = '{"id":"x","event":"t.stale","payload":{},"retry_count":0}'
            mock_redis.lpush('event_bus:processing', raw)
            mock_redis.hset('event_bus:processing:ts', raw, 0)

            assert event_bus._reap_stale(mock_redis) == 1
            assert mock_redis.llen('event_bus:processing') == 0
            assert mock_redis.llen('event_bus:queue') == 1
            assert mock_redis.hgetall('event_bus:processing:ts') == {}

    def test_reap_keeps_fresh(self, app, mock_redis):
        import time as _t

        from app.common.events import event_bus
        with app.app_context():
            raw = '{"id":"y","event":"t.fresh","payload":{},"retry_count":0}'
            mock_redis.lpush('event_bus:processing', raw)
            mock_redis.hset('event_bus:processing:ts', raw, _t.time())

            assert event_bus._reap_stale(mock_redis) == 0
            assert mock_redis.llen('event_bus:processing') == 1

    def test_visibility_timeout_configurable(self, app, mock_redis, monkeypatch):
        import time as _t

        from app.common.events import event_bus
        monkeypatch.setitem(app.config, 'EVENT_BUS_VISIBILITY_TIMEOUT', 3600)
        with app.app_context():
            raw = '{"id":"z","event":"t.cfg","payload":{},"retry_count":0}'
            mock_redis.lpush('event_bus:processing', raw)
            mock_redis.hset('event_bus:processing:ts', raw, _t.time() - 120)

            # 默认(60s)会判定超时回收，这里配置为 3600s -> 不回收
            assert event_bus._reap_stale(mock_redis) == 0
            assert mock_redis.llen('event_bus:processing') == 1


class TestEventBusLifecycle:
    def _patch_thread(self, monkeypatch, alive, started):
        from app.common import events as events_mod

        class DummyThread:
            def __init__(self, target=None, daemon=None):
                self.target = target

            def start(self):
                started['started'] = True

            def is_alive(self):
                return alive

            def join(self, timeout=None):
                pass

        monkeypatch.setattr(events_mod.threading, 'Thread', DummyThread)

    def test_start_after_preload_fork_restarts_consumer(self, app, monkeypatch):
        """fork 后继承 _running=True 但线程不存在，start 必须重新启动消费者"""
        from app.common.events import event_bus
        started = {}
        self._patch_thread(monkeypatch, alive=False, started=started)
        event_bus._running = True
        event_bus._consumer_thread = None
        try:
            event_bus.start(app)
            assert started.get('started') is True
        finally:
            event_bus._running = False
            event_bus._consumer_thread = None

    def test_start_noop_when_thread_alive(self, app, monkeypatch):
        """已有存活消费线程时，start 不重复启动"""
        from app.common import events as events_mod
        from app.common.events import event_bus
        started = {}
        self._patch_thread(monkeypatch, alive=True, started=started)
        event_bus._running = True
        event_bus._consumer_thread = events_mod.threading.Thread()
        try:
            event_bus.start(app)
            assert 'started' not in started
        finally:
            event_bus._running = False
            event_bus._consumer_thread = None
