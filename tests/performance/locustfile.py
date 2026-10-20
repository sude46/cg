# tests/performance/locustfile.py
"""Feed 读路径压测。

用 seed_tokens.py 预生成的 token 做认证，避免登录/注册的严格限流
（login 10/min、register 5/min 是路由级限流，不适合压测同时登录）。

运行：
    PERF_TOKENS_FILE=/tmp/perf_tokens.json \
    locust -f tests/performance/locustfile.py --headless \
           -u 40 -r 8 -t 60s --host http://127.0.0.1:5000 \
           --csv tests/performance/results/locust_feed
"""
import itertools
import json
import os
import threading

from locust import HttpUser, between, events, task

# 业务 SLA（可按环境调整）：读路径 P95 与错误率
SLA_P95_LATENCY = 500      # ms
SLA_ERROR_RATE = 0.001     # 0.1%

TOKENS = []
_token_lock = threading.Lock()
_token_seq = itertools.count()


@events.init.add_listener
def _load_tokens(environment, **kwargs):
    path = os.getenv('PERF_TOKENS_FILE', '')
    if not path or not os.path.exists(path):
        raise RuntimeError(f'PERF_TOKENS_FILE 不存在: {path!r}，请先运行 seed_tokens.py')
    with open(path, encoding='utf-8') as f:
        TOKENS.extend(json.load(f))
    if not TOKENS:
        raise RuntimeError('token 列表为空')


def _next_token():
    with _token_lock:
        idx = next(_token_seq)
    return TOKENS[idx % len(TOKENS)]


class FeedUser(HttpUser):
    """模拟登录用户刷时间线/广场/帖子列表（读多写少）。"""

    wait_time = between(0.8, 1.5)  # 约 0.7-1.2 req/s/用户，低于默认 100/min 限流

    def on_start(self):
        self.token = _next_token()

    def _headers(self):
        return {'Authorization': f'Bearer {self.token}'}

    @task(5)
    def timeline(self):
        self.client.get('/feeds/timeline?limit=20', headers=self._headers(),
                        name='/feeds/timeline')

    @task(3)
    def explore(self):
        self.client.get('/feeds/explore?limit=20', headers=self._headers(),
                        name='/feeds/explore')

    @task(2)
    def post_list(self):
        self.client.get('/posts?page=1&per_page=20', headers=self._headers(),
                        name='/posts')


@events.test_stop.add_listener
def _sla_summary(environment, **kwargs):
    s = environment.stats.total
    p95 = s.get_response_time_percentile(0.95)
    print('\n===== SLA 汇总 =====')
    print(f'请求数: {s.num_requests}  失败数: {s.num_failures}  '
          f'错误率: {s.fail_ratio:.4%}')
    print(f'吞吐: {s.total_rps:.2f} req/s   P95: {p95:.1f}ms   '
          f'P99: {s.get_response_time_percentile(0.99):.1f}ms')
    ok = p95 <= SLA_P95_LATENCY and s.fail_ratio <= SLA_ERROR_RATE
    print(('PASS' if ok else 'FAIL') +
          f'  (阈值: P95<={SLA_P95_LATENCY}ms, 错误率<={SLA_ERROR_RATE:.2%})')
