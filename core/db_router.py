"""主从读写路由。

Repository 读路径统一走这里：
- 优选健康从库；从库连接失败/连续失败 → 标记不健康并回落主库（带冷却试探恢复）
- 从库/主库回落均打点（DB_REPLICA_HEALTHY / DB_REPLICA_FAILOVER）与记日志
"""
import logging
import time

from flask_sqlalchemy.session import Session

from core import db
from core.metrics import DB_REPLICA_FAILOVER, DB_REPLICA_HEALTHY

logger = logging.getLogger(__name__)

REPLICA_FAIL_THRESHOLD = 2      # 连续失败多少次标记不健康
REPLICA_RECOVER_SECONDS = 30    # 不健康后冷却多久再试探


class MasterSlaveRouter:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._app = None
            cls._instance.replica_binds = []
            cls._instance._state = {}
            cls._instance._replica_idx = 0
        return cls._instance

    def init_app(self, app):
        self._app = app
        binds = app.config.get('SQLALCHEMY_BINDS', {}) or {}
        self.replica_binds = [
            key for key in binds
            if any(tag in key for tag in ('replica', 'slave', 'read'))
        ]
        self._state = {
            key: {'healthy': True, 'fail_count': 0, 'down_until': 0.0}
            for key in self.replica_binds
        }
        logger.info(f'DB路由初始化：主库*1，从库*{len(self.replica_binds)}')

    def _probe(self, bind: str) -> bool:
        """探测从库连通性（每次读都探测，保证绝不把请求打到已挂从库）。"""
        try:
            engine = db.get_engine(bind=bind)
            with engine.connect() as conn:
                conn.exec_driver_sql('SELECT 1')
            self._mark_success(bind)
            return True
        except Exception as e:
            self._mark_failure(bind)
            logger.warning(f'从库 {bind} 探测失败: {e}')
            return False

    def _mark_success(self, bind: str):
        state = self._state[bind]
        state['fail_count'] = 0
        state['healthy'] = True
        DB_REPLICA_HEALTHY.labels(bind=bind).set(1)

    def _mark_failure(self, bind: str):
        state = self._state[bind]
        state['fail_count'] += 1
        if state['fail_count'] >= REPLICA_FAIL_THRESHOLD:
            state['healthy'] = False
            state['down_until'] = time.time() + REPLICA_RECOVER_SECONDS
            logger.warning(
                f'从库 {bind} 连续失败 {state["fail_count"]} 次，'
                f'标记不健康 {REPLICA_RECOVER_SECONDS}s'
            )
        DB_REPLICA_HEALTHY.labels(bind=bind).set(0)

    def get_read_session(self):
        """返回读会话：优选健康从库；无可用从库时回落主库。"""
        if not self.replica_binds:
            return db.session

        now = time.time()
        for _ in range(len(self.replica_binds)):
            bind = self.replica_binds[self._replica_idx % len(self.replica_binds)]
            self._replica_idx += 1
            state = self._state[bind]
            if not state['healthy'] and now < state['down_until']:
                continue
            if self._probe(bind):
                return Session(db, bind=db.get_engine(bind=bind))

        DB_REPLICA_FAILOVER.labels(bind='all').inc()
        logger.warning('没有健康的从库，读操作回落主库')
        return db.session


db_router = MasterSlaveRouter()
