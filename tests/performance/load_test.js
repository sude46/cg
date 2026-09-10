// tests/performance/load_test.js
import http from 'k6/http';
import { sleep, check, trend } from 'k6';

// 定义SLA趋势
const P95_LATENCY = trend('p95_latency');
const THROUGHPUT = trend('throughput');

// 配置压测参数
export const options = {
  vus: 100, // 并发用户数
  duration: '60s', // 压测时长
  thresholds: {
    // SLA阈值
    'p95_latency': ['p(95)<500'], // p95≤500ms
    'http_req_failed': ['rate<0.001'], // 错误率≤0.1%
    'http_reqs': ['rate>100'], // 吞吐量≥100 QPS
  },
};

// 测试数据
const TEST_USERNAME = 'performance_test_user';
const TEST_PASSWORD = '12345678';
const TEST_POST_CONTENT = '性能测试：批量创建帖子的测试内容';

export default function () {
  let token = '';
  const baseUrl = 'http://localhost:5000/api';

  // 1. 登录获取token
  const loginRes = http.post(`${baseUrl}/auth/login`, JSON.stringify({
    username: TEST_USERNAME,
    password: TEST_PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' } });
  check(loginRes, { '登录成功': (r) => r.status === 200 });
  if (loginRes.status === 200) {
    token = loginRes.json().token;
  }

  // 2. 创建帖子
  if (token) {
    const createPostRes = http.post(`${baseUrl}/posts/create`, JSON.stringify({
      content: TEST_POST_CONTENT,
    }), {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
    });
    check(createPostRes, { '创建帖子成功': (r) => r.status === 200 });
    P95_LATENCY.add(createPostRes.timings.duration);
  }

  // 3. 查询帖子列表
  const listRes = http.get(`${baseUrl}/posts/list?page=1&page_size=10`);
  check(listRes, { '查询帖子列表成功': (r) => r.status === 200 });
  P95_LATENCY.add(listRes.timings.duration);
  THROUGHPUT.add(1);

  // 操作间隔
  sleep(1);
}