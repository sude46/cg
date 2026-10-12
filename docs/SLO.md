# SLO.md — 服务等级目标与可观测性

> 范围：weibo 平台后端（Flask API + Celery 异步）及其依赖（MySQL 主从 / Redis 哨兵 / Elasticsearch）。
> 指标来自 `/metrics`（Prometheus），链路来自 OpenTelemetry → Jaeger。
> 目标值是**工程默认值**，按业务与容量可调。

---

## 1. 关键用户旅程

| 旅程 | 说明 | 同步/异步 |
|---|---|---|
| 登录/注册 | 认证、签发 token | 同步 |
| 发帖 / 编辑 / 删除 | 帖子 CRUD | 同步 + 异步（Feed 推送、ES 索引） |
| 时间线 / 广场 | 关注流、全站广场 | 同步（Redis + DB 兜底） |
| 关注 / 点赞 / 评论 | 社交互动 | 同步（Redis 优先）+ 异步落库 |
| 通知 / 私信 | 未读数、实时推送 | SSE（Redis Pub/Sub）+ 同步接口 |
| 搜索 | 全文/子串检索 | 同步（ES，故障降级 DB） |

---

## 2. SLI / SLO 总表

窗口：**30 天滚动**。可用性/延迟按非健康请求统计。

| 维度 | SLI（指标） | SLO | 错误预算(30d) |
|---|---|---|---|
| 可用性 | `1 - 5xx占比`（`weibo_http_requests_total`） | **≥ 99.5%** | 3h36m |
| API 延迟 | P95（`weibo_http_request_duration_seconds`） | **≤ 300ms** | — |
| API 延迟 | P99 | **≤ 800ms** | — |
| DB 延迟 | P99（`weibo_db_query_duration_seconds`） | **≤ 200ms** | — |
| 从库健康 | `weibo_db_replica_healthy == 1` | **≥ 99.9%** | — |
| 读回落率 | `rate(weibo_db_replica_failover_total[5m])` | **≈ 0**（< 1/s） | — |
| MySQL 主从延迟 | `mysql_slave_status_seconds_behind_master` P99 | **≤ 1s**（严重 > 3s） | — |
| Redis 主从延迟 | `redis_master_last_io_seconds_ago` P99 | **≤ 1s** | — |
| 强一致窗口代价 | `rate(weibo_read_forced_master_total[5m])` | 观察项（无硬目标） | — |
| 数据一致性 | `weibo_reconcile_diff_count` | **= 0** | 0 |
| 异步成功率 | Celery `success/(success+failure)`（`weibo_celery_tasks_total`） | **≥ 99%** | 7h12m |
| 异步积压 | `celery_queue_length` | **< 500**（瞬时 < 1000） | — |
| 缓存命中 | `weibo_redis_cache_hit_rate{cache_type}` 均值 | feed/post/like **≥ 0.7** | — |
| 业务成功率 | 各 `weibo_*_operations_total{result="success"}` 占比 | **≥ 99%** | — |
| 搜索一致性 | `weibo_reconcile_diff_count{resource_type="search"}` | **= 0** | 0 |

> 说明：`reconcile_diff_count` 由对账任务写入（like/post/feed/comment/user/search）。`search` 维度来自 `reconcile_search_index`。

---

## 3. 错误预算与告警策略

### 3.1 预算计算（可用性 99.5% / 30d）
```
预算时长 = 30d × (1 - 0.995) = 3h36m
已消耗 = 5xx 请求数 / 总请求数 / (1 - 0.995)
```

### 3.2 多窗口燃烧率（示例，建议新增规则）
| 严重度 | 条件 | 含义 |
|---|---|---|
| 快烧 (page) | 1h 燃烧率 > 14.4 | 2 天内烧完预算 |
| 慢烧 (ticket) | 6h 燃烧率 > 6 | 30 天窗口告警 |
| 预算耗尽 | 30d 消耗 > 100% | 冻结发布、优先修复 |

```promql
# 1h 燃烧率（基于 5xx/总量）
(
  sum(rate(weibo_http_requests_total{status_code=~"5.."}[1h]))
  / sum(rate(weibo_http_requests_total[1h]))
) / (1 - 0.995)
```

### 3.3 与现有告警的对应
`monitoring/prometheus/rules/weibo_rules.yml` 已覆盖：
- `WeiboApiHighLatency`（P99>500ms, 2m）
- `WeiboApiHighErrorRate`（5xx>1%, 2m）
- `WeiboCeleryQueueBacklog`（`celery_queue_length>1000`, 1m）
- `WeiboRedisMemoryHigh`（>80%, 5m）
- `WeiboDbSlowQuery`（DB P99>500ms, 3m）
- `WeiboMysqlDown`（`up{job="mysql-master"}==0`, 1m）
- `WeiboReconcileDiff`（`weibo_reconcile_diff_count>0`, 1m）
- `WeiboMysqlReplicationLag`（从库延迟>1s, 2m）/ `WeiboMysqlReplicationLagCritical`（>3s, 1m）
- `WeiboMysqlReplicaNotRunning`（`Slave_IO/SQL_Running` 非 1, 1m）
- `WeiboRedisReplicationLag`（`redis_master_last_io_seconds_ago>1`, 2m）
- `WeiboRedisReplicaLinkDown`（`redis_master_link_up==0`, 1m）

**待补**：从库不健康（`weibo_db_replica_healthy==0`）、Celery 失败率、搜索对账差异（可用现有 `WeiboReconcileDiff` 覆盖，因它不区分 label）。

---

## 4. PromQL 速查

```promql
# 可用性（30d）
1 - (
  sum(increase(weibo_http_requests_total{status_code=~"5.."}[30d]))
  / sum(increase(weibo_http_requests_total[30d]))
)

# 接口 P95（5m）
histogram_quantile(0.95, sum(rate(weibo_http_request_duration_seconds_bucket[5m])) by (le, endpoint))

# 按接口的 5xx 比例
sum(rate(weibo_http_requests_total{status_code=~"5.."}[5m])) by (endpoint)
/ sum(rate(weibo_http_requests_total[5m])) by (endpoint)

# DB P99（按表）
histogram_quantile(0.99, sum(rate(weibo_db_query_duration_seconds_bucket[5m])) by (le, table))

# Celery 失败率（5m）
sum(rate(weibo_celery_tasks_total{status="failure"}[5m]))
/ clamp_min(sum(rate(weibo_celery_tasks_total[5m])), 1)

# 对账差异（各资源）
weibo_reconcile_diff_count

# 从库健康 / 回落
weibo_db_replica_healthy
rate(weibo_db_replica_failover_total[5m])

# 主从延迟（MySQL / Redis 从库 exporter）
mysql_slave_status_seconds_behind_master{job="mysql-replica"}
redis_master_last_io_seconds_ago{job=~"redis-replica-.*"}

# 强一致窗口代价（窗口内强制读主库的速率）
sum(rate(weibo_read_forced_master_total[5m])) by (resource)
```

---

## 5. 采集与展示

| 组件 | 地址 | 用途 |
|---|---|---|
| 应用 `/metrics` | `app:5000/metrics` | 业务/HTTP/DB/Redis/Celery 指标 |
| Prometheus | `:9090` | 抓取与告警规则 |
| Alertmanager | `:9093` | 告警路由（钉钉 webhook） |
| Grafana | `:3000` | 面板 |
| Loki | `:3100` | 日志（含 `request_id`/`trace_id` 关联） |
| Jaeger | `:16686` | 分布式追踪（`weibo-api` / `weibo-worker`） |

抓取目标见 `monitoring/prometheus/prometheus.yml`：`weibo-api(app:5000)`、node、redis-business、mysql-master、mysql-replica、redis-replica-1/2、celery、alert-webhook。
追踪：HTTP → SQL → 自研事件总线 → Celery → ES 已贯通（见 `core/tracing.py`）。

---

## 6. 已知限制（SLO 不承诺的部分）

1. **异步事件非投递保证**：自研事件总线为 Redis List **单消费者 BRPOP**，失败最多重试 3 次后丢弃；多进程下不广播（SSE 已改用 Pub/Sub）。→ 异步链路只承诺"尽力而为 + 对账兜底"。
2. **私信未读数**：`chats` 用 `ConversationUser.unread_count` 求和（DB SELECT）；尚未做 Redis 计数与对账，热点会话量大时延迟会上升。
3. **搜索依赖 ES**：ES 故障时降级为 DB `ILIKE`（短 TTL 缓存），召回与延迟都不能按 ES 目标承诺；重建索引期间结果可能暂缺。
4. **缓存一致性**：Cache-Aside + 延迟双删（写后立即删缓存，再由 Celery `delayed_invalidate` 在约 2s 后二次删）；帖子 `recent_modify` 强一致标记窗口默认 5s，通知未读数为 **60s**（`NotificationCache.RECENT_MODIFY_TTL=60`）：窗口内读强制走主库，避免主从延迟回跳旧值。整体为**最终一致**，不接受强一致读承诺。延迟双删的 `countdown=2s` 与窗口 TTL 目前是工程默认值，**应依据 `mysql_slave_status_seconds_behind_master` / `redis_master_last_io_seconds_ago` 的实测 P99 校准**（建议 `countdown = max(2s, 2×P99)`，`窗口 TTL = countdown + P99`）。
5. **无前端 RUM**：仅服务端指标，页面级可用性/交互延迟不在本 SLO 内。
6. **无自动 Trace-SLO**：Jaeger 用于排障与人工核对，暂未用 trace 数据自动计算 SLO。
7. **单实例 beat**：`beat_schedule` 依赖单个 `celery-beat`，多实例会重复触发；对账/热榜属幂等任务，可容忍。
8. **SSE 并发上限**：生产镜像 `gunicorn -w4 -k gthread --threads 2` → 约 **8** 个工作线程，每条 SSE 长连接独占 1 个线程，故并发 SSE 上限约 8（通知流 + 私信流各占 1）；需更高并发应调大 `--threads` 或改用 gevent/eventlet。当前以宿主 nginx `proxy_read_timeout 3600s` + 后端 20s 心跳保活。

---

## 7. 文档维护

- 新增关键接口/异步链路时，同步更新第 1、2 节与 `weibo_rules.yml`。
- 调整 SLO 目标需评估错误预算与容量，并记录变更原因。
