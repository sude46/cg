# tests/performance/locustfile.py
import random
from locust import HttpUser, task, between, tag
from locust.stats import RequestStats

# 设定SLA阈值（可根据业务调整）
SLA_P95_LATENCY = 500  # p95响应时间≤500ms
SLA_THROUGHPUT = 100    # 吞吐量≥100 QPS
SLA_ERROR_RATE = 0.001  # 错误率≤0.1%

# 全局测试数据
TEST_USERNAME = "performance_test_user"
TEST_PASSWORD = "12345678"
TEST_POST_CONTENT = "性能测试：批量创建帖子的测试内容"

class PostAppUser(HttpUser):
    """性能测试用户行为模拟"""
    wait_time = between(1, 3)  # 每个用户操作间隔1-3秒
    token = None
    post_ids = []  # 存储创建的帖子ID，用于后续点赞/评论

    def on_start(self):
        """用户初始化：登录获取token"""
        # 1. 先注册测试用户（若未存在）
        self.client.post(
            "/api/auth/register",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        # 2. 登录获取token
        login_response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        if login_response.status_code == 200:
            self.token = login_response.json()["token"]
        else:
            print("登录失败，无法进行后续测试")

    @tag("login")
    @task(1)
    def test_login(self):
        """测试登录接口性能"""
        self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )

    @tag("create_post")
    @task(3)  # 权重3，执行频率更高
    def test_create_post(self):
        """测试创建帖子接口性能"""
        if not self.token:
            return
        response = self.client.post(
            "/api/posts/create",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"content": TEST_POST_CONTENT}
        )
        if response.status_code == 200:
            self.post_ids.append(response.json()["id"])

    @tag("like_post")
    @task(2)
    def test_like_post(self):
        """测试点赞接口性能"""
        if not self.token or not self.post_ids:
            return
        post_id = random.choice(self.post_ids)
        self.client.post(
            "/api/posts/like",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"post_id": post_id, "request_id": f"perf_{random.randint(1000, 9999)}"}
        )

    @tag("get_post_list")
    @task(4)
    def test_get_post_list(self):
        """测试查询帖子列表接口性能"""
        self.client.get(
            "/api/posts/list",
            params={"page": 1, "page_size": 10}
        )

# 压测结束后验证SLA
def check_sla(environment, **kwargs):
    """验证SLA是否达标"""
    stats = RequestStats()
    # 1. 验证p95响应时间
    p95_latency = stats.get_current_response_time_percentile(0.95)
    # 2. 验证吞吐量（RPS）
    throughput = stats.total_rps
    # 3. 验证错误率
    error_rate = stats.total_failures / (stats.total_requests or 1)

    print(f"\n===== SLA验证结果 =====")
    print(f"p95响应时间: {p95_latency:.2f}ms (阈值: {SLA_P95_LATENCY}ms)")
    print(f"吞吐量: {throughput:.2f} QPS (阈值: {SLA_THROUGHPUT} QPS)")
    print(f"错误率: {error_rate:.4f} (阈值: {SLA_ERROR_RATE})")

    # 不达标则退出码非0
    if p95_latency > SLA_P95_LATENCY or throughput < SLA_THROUGHPUT or error_rate > SLA_ERROR_RATE:
        print("❌ SLA验证不通过！")
        environment.process_exit_code = 1
    else:
        print("✅ SLA验证通过！")

# 注册SLA检查钩子
from locust import events
events.test_stop.add_listener(check_sla)