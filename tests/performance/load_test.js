// tests/performance/load_test.js
// Feed 读路径 k6 压测（与 locustfile.py 场景一致）。
// token 用 seed_tokens.py 预生成：
//   PERF_TOKEN=<access_token> k6 run tests/performance/load_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 40,
  duration: '60s',
  thresholds: {
    http_req_failed: ['rate<0.001'],       // 错误率 <= 0.1%
    'http_req_duration{name:timeline}': ['p(95)<500'],
    'http_req_duration{name:explore}': ['p(95)<500'],
    'http_req_duration{name:posts}': ['p(95)<500'],
  },
};

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:5000';
const TOKEN = __ENV.PERF_TOKEN || '';
const HEADERS = { Authorization: `Bearer ${TOKEN}` };

export default function () {
  const timeline = http.get(`${BASE}/feeds/timeline?limit=20`,
    { headers: HEADERS, tags: { name: 'timeline' } });
  check(timeline, { 'timeline 200/304': (r) => r.status === 200 || r.status === 304 });

  const explore = http.get(`${BASE}/feeds/explore?limit=20`,
    { headers: HEADERS, tags: { name: 'explore' } });
  check(explore, { 'explore 200': (r) => r.status === 200 });

  const posts = http.get(`${BASE}/posts?page=1&per_page=20`,
    { headers: HEADERS, tags: { name: 'posts' } });
  check(posts, { 'posts 200': (r) => r.status === 200 });

  sleep(1);
}
